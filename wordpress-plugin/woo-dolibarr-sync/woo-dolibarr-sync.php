<?php
/**
 * Plugin Name: WooDoliSync — WooCommerce → Dolibarr Sync
 * Plugin URI:  https://github.com/Carlitos6712/harvist
 * Description: Sincronización bidireccional entre WooCommerce y Dolibarr ERP.
 *              Sync de productos, stock, pedidos e inventario.
 * Version:     1.1.0
 * Author:      Carlitos6712
 * Requires WC: 8.0
 * Requires PHP: 8.1
 *
 * @package WooDoliSync
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

define( 'WDS_VERSION',  '1.1.0' );
define( 'WDS_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );

/**
 * Inicializa el plugin cuando WooCommerce está activo.
 */
function wds_init(): void {
    if ( ! class_exists( 'WooCommerce' ) ) {
        add_action( 'admin_notices', static function (): void {
            echo '<div class="notice notice-error"><p><strong>WooDoliSync</strong> requiere WooCommerce activo.</p></div>';
        } );
        return;
    }

    require_once WDS_PLUGIN_DIR . 'includes/class-doli-api.php';
    require_once WDS_PLUGIN_DIR . 'includes/class-customer-sync.php';
    require_once WDS_PLUGIN_DIR . 'includes/class-order-sync.php';
    require_once WDS_PLUGIN_DIR . 'includes/class-product-sync.php';
    require_once WDS_PLUGIN_DIR . 'admin/settings-page.php';

    $url   = get_option( 'wds_dolibarr_url', '' );
    $token = get_option( 'wds_dolibarr_token', '' );

    if ( ! $url || ! $token ) {
        return;
    }

    $api          = new WDS_Doli_API( $url, $token );
    $product_sync = new WDS_Product_Sync( $api );
    $product_sync->register_hooks();

    $customer_sync = new WDS_Customer_Sync( $api );
    $customer_sync->register_hooks();

    $order_sync = new WDS_Order_Sync( $api, $customer_sync );
    $order_sync->register_hooks();

    $settings = new WDS_Settings_Page( $product_sync );
    $settings->register();
}
add_action( 'plugins_loaded', 'wds_init' );

/**
 * Activa el cron diario de reintentos al activar el plugin.
 */
register_activation_hook( __FILE__, static function (): void {
    if ( ! wp_next_scheduled( 'wds_daily_retry' ) ) {
        wp_schedule_event( time(), 'daily', 'wds_daily_retry' );
    }
} );

/**
 * Elimina el cron diario al desactivar el plugin.
 */
register_deactivation_hook( __FILE__, static function (): void {
    wp_clear_scheduled_hook( 'wds_daily_retry' );
} );
