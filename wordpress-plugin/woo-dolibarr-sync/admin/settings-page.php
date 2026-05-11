<?php
/**
 * Página de ajustes del plugin WooDoliSync en el admin de WordPress.
 *
 * Acceso: WooCommerce → Dolibarr Sync
 *
 * Incluye:
 * - Campos de configuración (URL + token Dolibarr).
 * - Tabla de retry queue con estado de reintentos.
 * - Botón "Vaciar cola" para limpiar wds_retry_queue.
 * - Botón "Test conexión" que llama GET /api/index.php/status.
 *
 * @package WooDoliSync
 * @author  Carlitos6712
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

class WDS_Settings_Page {

    /** @var WDS_Product_Sync */
    private WDS_Product_Sync $product_sync;

    /**
     * @param WDS_Product_Sync $product_sync Instancia del servicio de sync.
     */
    public function __construct( WDS_Product_Sync $product_sync ) {
        $this->product_sync = $product_sync;
    }

    /**
     * Registra la página de ajustes en el menú de WooCommerce.
     */
    public function register(): void {
        add_submenu_page(
            'woocommerce',
            'Dolibarr Sync',
            'Dolibarr Sync',
            'manage_woocommerce',
            'wds-settings',
            [ $this, 'render' ]
        );
        add_action( 'admin_init', [ $this, 'register_settings' ] );
        add_action( 'admin_post_wds_flush_queue',    [ $this, 'handle_flush_queue' ] );
        add_action( 'admin_post_wds_test_connection', [ $this, 'handle_test_connection' ] );
    }

    /**
     * Registra las opciones de configuración con la Settings API de WordPress.
     */
    public function register_settings(): void {
        register_setting( 'wds_settings_group', 'wds_dolibarr_url', [
            'type'              => 'string',
            'sanitize_callback' => 'esc_url_raw',
            'default'           => '',
        ] );
        register_setting( 'wds_settings_group', 'wds_dolibarr_token', [
            'type'              => 'string',
            'sanitize_callback' => 'sanitize_text_field',
            'default'           => '',
        ] );
    }

    /**
     * Vacía la retry queue y redirige de vuelta a la página de ajustes.
     */
    public function handle_flush_queue(): void {
        if ( ! current_user_can( 'manage_woocommerce' ) ) {
            wp_die( 'No autorizado.' );
        }
        check_admin_referer( 'wds_flush_queue' );
        $this->product_sync->flush_retry_queue();
        wp_safe_redirect( add_query_arg( [ 'page' => 'wds-settings', 'flushed' => '1' ], admin_url( 'admin.php' ) ) );
        exit;
    }

    /**
     * Prueba la conexión con Dolibarr y redirige con el resultado.
     */
    public function handle_test_connection(): void {
        if ( ! current_user_can( 'manage_woocommerce' ) ) {
            wp_die( 'No autorizado.' );
        }
        check_admin_referer( 'wds_test_connection' );

        $url   = get_option( 'wds_dolibarr_url', '' );
        $token = get_option( 'wds_dolibarr_token', '' );

        if ( ! $url || ! $token ) {
            wp_safe_redirect( add_query_arg( [ 'page' => 'wds-settings', 'conn_error' => 'missing_config' ], admin_url( 'admin.php' ) ) );
            exit;
        }

        $api      = new WDS_Doli_API( $url, $token );
        $response = $api->get( 'status' );

        if ( is_wp_error( $response ) ) {
            wp_safe_redirect( add_query_arg( [
                'page'       => 'wds-settings',
                'conn_error' => rawurlencode( $response->get_error_message() ),
            ], admin_url( 'admin.php' ) ) );
        } else {
            $version = isset( $response['dolibarr_version'] ) ? $response['dolibarr_version'] : 'desconocida';
            wp_safe_redirect( add_query_arg( [
                'page'     => 'wds-settings',
                'conn_ok'  => '1',
                'doli_ver' => rawurlencode( $version ),
            ], admin_url( 'admin.php' ) ) );
        }
        exit;
    }

    /**
     * Renderiza la página de ajustes completa.
     */
    public function render(): void {
        if ( ! current_user_can( 'manage_woocommerce' ) ) {
            wp_die( 'No autorizado.' );
        }

        $queue      = $this->product_sync->get_retry_queue();
        $doli_url   = get_option( 'wds_dolibarr_url', '' );
        $doli_token = get_option( 'wds_dolibarr_token', '' );
        ?>
        <div class="wrap">
            <h1>WooDoliSync — Configuración</h1>

            <?php if ( isset( $_GET['settings-updated'] ) ) : ?>
                <div class="notice notice-success is-dismissible"><p>Configuración guardada.</p></div>
            <?php endif; ?>

            <?php if ( isset( $_GET['flushed'] ) ) : ?>
                <div class="notice notice-success is-dismissible"><p>Cola de reintentos vaciada.</p></div>
            <?php endif; ?>

            <?php if ( isset( $_GET['conn_ok'] ) ) : ?>
                <div class="notice notice-success is-dismissible">
                    <p>✅ Conexión correcta — Dolibarr versión: <strong><?php echo esc_html( urldecode( $_GET['doli_ver'] ?? '' ) ); ?></strong></p>
                </div>
            <?php endif; ?>

            <?php if ( isset( $_GET['conn_error'] ) ) : ?>
                <div class="notice notice-error is-dismissible">
                    <p>❌ Error de conexión: <?php echo esc_html( urldecode( $_GET['conn_error'] ) ); ?></p>
                </div>
            <?php endif; ?>

            <!-- ── Configuración ─────────────────────────────────────── -->
            <h2>Credenciales Dolibarr</h2>
            <form method="post" action="options.php">
                <?php settings_fields( 'wds_settings_group' ); ?>
                <table class="form-table">
                    <tr>
                        <th scope="row"><label for="wds_dolibarr_url">URL de Dolibarr</label></th>
                        <td>
                            <input
                                type="url"
                                name="wds_dolibarr_url"
                                id="wds_dolibarr_url"
                                value="<?php echo esc_attr( $doli_url ); ?>"
                                class="regular-text"
                                placeholder="https://mi-dolibarr.com"
                            />
                            <p class="description">URL base sin trailing slash.</p>
                        </td>
                    </tr>
                    <tr>
                        <th scope="row"><label for="wds_dolibarr_token">DOLAPIKEY (token)</label></th>
                        <td>
                            <input
                                type="password"
                                name="wds_dolibarr_token"
                                id="wds_dolibarr_token"
                                value="<?php echo esc_attr( $doli_token ); ?>"
                                class="regular-text"
                                autocomplete="new-password"
                            />
                            <p class="description">Dolibarr → Inicio → Configuración → API/REST → Generar clave.</p>
                        </td>
                    </tr>
                </table>
                <?php submit_button( 'Guardar configuración' ); ?>
            </form>

            <!-- ── Test conexión ─────────────────────────────────────── -->
            <h2>Test de conexión</h2>
            <form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>">
                <input type="hidden" name="action" value="wds_test_connection" />
                <?php wp_nonce_field( 'wds_test_connection' ); ?>
                <?php submit_button( 'Probar conexión con Dolibarr', 'secondary', 'submit', false ); ?>
            </form>

            <!-- ── Retry queue ───────────────────────────────────────── -->
            <h2>Cola de reintentos</h2>

            <?php if ( empty( $queue ) ) : ?>
                <p>No hay elementos pendientes en la cola.</p>
            <?php else : ?>
                <p><?php echo count( $queue ); ?> elemento(s) pendiente(s).</p>
                <table class="widefat striped">
                    <thead>
                        <tr>
                            <th>Producto WC</th>
                            <th>Acción</th>
                            <th>Intentos</th>
                            <th>Último error</th>
                            <th>En cola desde</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ( $queue as $item ) : ?>
                            <tr>
                                <td>
                                    <?php
                                    $product = wc_get_product( $item['product_id'] );
                                    if ( $product ) {
                                        echo '<a href="' . esc_url( get_edit_post_link( $item['product_id'] ) ) . '">'
                                            . esc_html( $product->get_name() )
                                            . ' (#' . (int) $item['product_id'] . ')</a>';
                                    } else {
                                        echo '#' . (int) $item['product_id'];
                                    }
                                    ?>
                                </td>
                                <td><?php echo esc_html( $item['action'] ); ?></td>
                                <td><?php echo (int) $item['attempts']; ?></td>
                                <td><?php echo esc_html( substr( $item['last_error'] ?? '', 0, 120 ) ); ?></td>
                                <td>
                                    <?php
                                    if ( ! empty( $item['queued_at'] ) ) {
                                        echo esc_html( date_i18n( 'd/m/Y H:i', $item['queued_at'] ) );
                                    }
                                    ?>
                                </td>
                            </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>

                <br />
                <form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>">
                    <input type="hidden" name="action" value="wds_flush_queue" />
                    <?php wp_nonce_field( 'wds_flush_queue' ); ?>
                    <?php submit_button( 'Vaciar cola de reintentos', 'delete', 'submit', false, [ 'onclick' => 'return confirm("¿Seguro? Se perderán todos los intentos pendientes.")' ] ); ?>
                </form>
            <?php endif; ?>
        </div>
        <?php
    }
}
