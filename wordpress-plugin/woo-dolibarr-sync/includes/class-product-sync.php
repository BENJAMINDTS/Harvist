<?php
/**
 * Sincronización de productos WooCommerce ↔ Dolibarr.
 *
 * Cubre: create/update en save, delete en trash, stock en stock_change.
 * Implementa retry queue para fallos de API.
 *
 * @package WooDoliSync
 * @author  Carlitos6712
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

class WDS_Product_Sync {

    /** @var WDS_Doli_API */
    private WDS_Doli_API $api;

    /** @var string wp_options key de la cola de reintentos. */
    private const RETRY_QUEUE_KEY = 'wds_retry_queue';

    /**
     * @param WDS_Doli_API $api Cliente Dolibarr ya inicializado.
     */
    public function __construct( WDS_Doli_API $api ) {
        $this->api = $api;
    }

    // ── Hooks ────────────────────────────────────────────────────────────────

    /**
     * Registra todos los hooks WordPress/WooCommerce necesarios.
     */
    public function register_hooks(): void {
        add_action( 'woocommerce_update_product',        [ $this, 'on_product_save' ] );
        add_action( 'wp_trash_post',                     [ $this, 'on_product_trash' ] );
        add_action( 'before_delete_post',                [ $this, 'on_product_trash' ] );
        add_action( 'woocommerce_product_set_stock',     [ $this, 'on_stock_change' ] );
        add_action( 'wds_daily_retry',                   [ $this, 'process_retry_queue' ] );
    }

    // ── Mapeo de campos ──────────────────────────────────────────────────────

    /**
     * Construye el payload Dolibarr a partir de un producto WooCommerce.
     *
     * @param WC_Product $product Producto WooCommerce.
     * @return array Payload para la API de Dolibarr.
     */
    private function build_payload( WC_Product $product ): array {
        $is_published = 'publish' === $product->get_status();
        $ref          = $product->get_sku() ?: 'WC-' . $product->get_id();

        return [
            'label'       => $product->get_name(),
            'ref'         => $ref,
            'price'       => (float) $product->get_regular_price(),
            'price_ttc'   => (float) $product->get_price(),
            'description' => wp_strip_all_tags( $product->get_description() ),
            'note'        => wp_strip_all_tags( $product->get_short_description() ),
            'weight'      => (float) $product->get_weight(),
            'type'        => $product->is_virtual() ? 1 : 0,
            'stock_reel'  => (float) $product->get_stock_quantity(),
            'status'      => $is_published ? 1 : 0,
            'status_buy'  => $is_published ? 1 : 0,
        ];
    }

    // ── Sync on save ─────────────────────────────────────────────────────────

    /**
     * Hook woocommerce_update_product: crea o actualiza en Dolibarr.
     *
     * En caso de fallo, el producto se encola en retry queue.
     *
     * @param int $product_id ID del producto WooCommerce.
     */
    public function on_product_save( int $product_id ): void {
        $product = wc_get_product( $product_id );
        if ( ! $product ) {
            return;
        }

        // Procesar retry queue acumulada en este mismo save
        $this->process_retry_queue();

        $payload  = $this->build_payload( $product );
        $doli_id  = (int) get_post_meta( $product_id, '_doli_product_id', true );
        $doli_ref = get_post_meta( $product_id, '_doli_product_ref', true ) ?: $payload['ref'];

        if ( $doli_id ) {
            $result = $this->api->put( 'products/' . $doli_id, $payload );
        } else {
            // Comprobar si ya existe por ref
            $existing = $this->api->get( 'products?sqlfilters=(ref:=:\'' . rawurlencode( $doli_ref ) . '\')' );
            if ( ! is_wp_error( $existing ) && is_array( $existing ) && ! empty( $existing ) ) {
                $doli_id = (int) $existing[0]['id'];
                update_post_meta( $product_id, '_doli_product_id', $doli_id );
                update_post_meta( $product_id, '_doli_product_ref', $existing[0]['ref'] );
                $result = $this->api->put( 'products/' . $doli_id, $payload );
            } else {
                $result = $this->api->post( 'products', $payload );
                if ( ! is_wp_error( $result ) && isset( $result['id'] ) ) {
                    update_post_meta( $product_id, '_doli_product_id', (int) $result['id'] );
                    update_post_meta( $product_id, '_doli_product_ref', $payload['ref'] );
                }
            }
        }

        if ( is_wp_error( $result ) ) {
            error_log( '[WooDoliSync] on_product_save failed for WC product ' . $product_id . ': ' . $result->get_error_message() );
            $this->enqueue_retry( $product_id, 'save', $payload );
        }
    }

    // ── Sync on delete/trash ─────────────────────────────────────────────────

    /**
     * Hook wp_trash_post / before_delete_post: elimina en Dolibarr.
     *
     * Solo actúa si el post es un producto WooCommerce.
     *
     * @param int $post_id ID del post.
     */
    public function on_product_trash( int $post_id ): void {
        if ( 'product' !== get_post_type( $post_id ) ) {
            return;
        }

        $doli_id = (int) get_post_meta( $post_id, '_doli_product_id', true );
        if ( ! $doli_id ) {
            return;
        }

        $result = $this->api->delete( 'products/' . $doli_id );

        if ( is_wp_error( $result ) ) {
            error_log( '[WooDoliSync] syncDelete failed for Dolibarr product ' . $doli_id . ': ' . $result->get_error_message() );
        } else {
            delete_post_meta( $post_id, '_doli_product_id' );
            delete_post_meta( $post_id, '_doli_product_ref' );
        }
    }

    // ── Sync stock ───────────────────────────────────────────────────────────

    /**
     * Hook woocommerce_product_set_stock: actualiza solo stock_reel en Dolibarr.
     *
     * Más eficiente que on_product_save — envía únicamente el campo cambiado.
     *
     * @param WC_Product $product Producto con stock actualizado.
     */
    public function on_stock_change( WC_Product $product ): void {
        $product_id = $product->get_id();
        $doli_id    = (int) get_post_meta( $product_id, '_doli_product_id', true );

        if ( ! $doli_id ) {
            return;
        }

        $result = $this->api->put( 'products/' . $doli_id, [
            'stock_reel' => (float) $product->get_stock_quantity(),
        ] );

        if ( is_wp_error( $result ) ) {
            error_log( '[WooDoliSync] syncStock failed for WC product ' . $product_id . ': ' . $result->get_error_message() );
            $this->enqueue_retry( $product_id, 'stock', [ 'stock_reel' => (float) $product->get_stock_quantity() ] );
        }
    }

    // ── Retry queue ──────────────────────────────────────────────────────────

    /**
     * Añade un item a la cola de reintentos.
     *
     * Estructura de cada item:
     *   { product_id, action, payload, attempts, last_error, queued_at }
     *
     * @param int    $product_id WooCommerce product ID.
     * @param string $action     "save" | "stock" | "delete".
     * @param array  $payload    Payload a reenviar.
     */
    private function enqueue_retry( int $product_id, string $action, array $payload ): void {
        $queue = $this->get_retry_queue();

        // Actualizar item existente si ya está en cola
        foreach ( $queue as &$item ) {
            if ( $item['product_id'] === $product_id && $item['action'] === $action ) {
                $item['payload']   = $payload;
                $item['attempts'] += 1;
                $item['queued_at'] = time();
                update_option( self::RETRY_QUEUE_KEY, wp_json_encode( $queue ) );
                return;
            }
        }
        unset( $item );

        $queue[] = [
            'product_id' => $product_id,
            'action'     => $action,
            'payload'    => $payload,
            'attempts'   => 1,
            'last_error' => '',
            'queued_at'  => time(),
        ];

        update_option( self::RETRY_QUEUE_KEY, wp_json_encode( $queue ) );
    }

    /**
     * Procesa la cola de reintentos. Llamado en cada save y por WP-Cron daily.
     *
     * Items procesados con éxito se eliminan de la cola.
     * Items con > 5 intentos se eliminan con log de error.
     */
    public function process_retry_queue(): void {
        $queue     = $this->get_retry_queue();
        $remaining = [];

        foreach ( $queue as $item ) {
            if ( $item['attempts'] > 5 ) {
                error_log( '[WooDoliSync] Retry queue: dropping product ' . $item['product_id'] . ' after 5 attempts.' );
                continue;
            }

            $product = wc_get_product( $item['product_id'] );
            $doli_id = $product ? (int) get_post_meta( $item['product_id'], '_doli_product_id', true ) : 0;

            if ( 'stock' === $item['action'] && $doli_id ) {
                $result = $this->api->put( 'products/' . $doli_id, $item['payload'] );
            } elseif ( 'save' === $item['action'] && $product ) {
                $result = $doli_id
                    ? $this->api->put( 'products/' . $doli_id, $item['payload'] )
                    : $this->api->post( 'products', $item['payload'] );
            } elseif ( 'delete' === $item['action'] && $doli_id ) {
                $result = $this->api->delete( 'products/' . $doli_id );
            } else {
                continue; // Skip — producto ya no existe o no tiene doli_id
            }

            if ( is_wp_error( $result ) ) {
                $item['attempts'] += 1;
                $item['last_error'] = $result->get_error_message();
                $remaining[]        = $item;
            }
        }

        update_option( self::RETRY_QUEUE_KEY, wp_json_encode( $remaining ) );
    }

    /**
     * Devuelve la cola de reintentos actual.
     *
     * @return array Lista de items pendientes.
     */
    public function get_retry_queue(): array {
        $raw = get_option( self::RETRY_QUEUE_KEY, '[]' );
        $q   = json_decode( $raw, true );
        return is_array( $q ) ? $q : [];
    }

    /**
     * Vacía la cola de reintentos.
     */
    public function flush_retry_queue(): void {
        update_option( self::RETRY_QUEUE_KEY, '[]' );
    }
}
