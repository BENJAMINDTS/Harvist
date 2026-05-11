<?php
/**
 * Cliente HTTP hacia la API REST de Dolibarr.
 *
 * Toda comunicación con Dolibarr pasa por esta clase.
 * NUNCA usar wp_remote_* directamente desde otros módulos.
 *
 * @package WooDoliSync
 * @author  Carlitos6712
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

class WDS_Doli_API {

    /** @var string URL base de Dolibarr (sin trailing slash). */
    private string $base_url;

    /** @var string Token DOLAPIKEY. */
    private string $token;

    /** @var string Prefijo de cache para GET requests (60s TTL). */
    private const CACHE_GROUP = 'wds_doli_api';

    /** @var int TTL de caché GET en segundos. */
    private const CACHE_TTL = 60;

    /**
     * @param string $base_url URL base de Dolibarr (ej: https://mi-dolibarr.com).
     * @param string $token    DOLAPIKEY.
     */
    public function __construct( string $base_url, string $token ) {
        $this->base_url = rtrim( $base_url, '/' );
        $this->token    = $token;
    }

    /**
     * Ejecuta una petición GET con caché de 60s.
     *
     * @param string $endpoint Ruta relativa (ej: "products?sqlfilters=...").
     * @return array|WP_Error Decoded JSON body o WP_Error.
     */
    public function get( string $endpoint ) {
        $cache_key = 'get_' . md5( $endpoint );
        $cached    = wp_cache_get( $cache_key, self::CACHE_GROUP );

        if ( false !== $cached ) {
            return $cached;
        }

        $response = $this->request( 'GET', $endpoint );

        if ( ! is_wp_error( $response ) ) {
            wp_cache_set( $cache_key, $response, self::CACHE_GROUP, self::CACHE_TTL );
        }

        return $response;
    }

    /**
     * Ejecuta una petición POST.
     *
     * @param string $endpoint Ruta relativa.
     * @param array  $body     Datos a enviar como JSON.
     * @return array|WP_Error
     */
    public function post( string $endpoint, array $body = [] ) {
        return $this->request( 'POST', $endpoint, $body );
    }

    /**
     * Ejecuta una petición PUT.
     *
     * @param string $endpoint Ruta relativa.
     * @param array  $body     Datos a actualizar.
     * @return array|WP_Error
     */
    public function put( string $endpoint, array $body = [] ) {
        return $this->request( 'PUT', $endpoint, $body );
    }

    /**
     * Ejecuta una petición DELETE.
     *
     * @param string $endpoint Ruta relativa (ej: "products/42").
     * @return array|WP_Error
     */
    public function delete( string $endpoint ) {
        return $this->request( 'DELETE', $endpoint );
    }

    /**
     * Petición HTTP base con autenticación DOLAPIKEY.
     *
     * Enmascara el token en error_log (últimos 32 chars reemplazados por ***).
     *
     * @param string $method   GET|POST|PUT|DELETE.
     * @param string $endpoint Ruta relativa a /api/index.php/.
     * @param array  $body     Body JSON (solo POST/PUT).
     * @return array|WP_Error Decoded JSON o WP_Error.
     */
    private function request( string $method, string $endpoint, array $body = [] ) {
        $url  = $this->base_url . '/api/index.php/' . ltrim( $endpoint, '/' );
        $args = [
            'method'  => $method,
            'headers' => [
                'DOLAPIKEY'    => $this->token,
                'Content-Type' => 'application/json',
                'Accept'       => 'application/json',
            ],
            'timeout' => 30,
        ];

        if ( ! empty( $body ) && in_array( $method, [ 'POST', 'PUT' ], true ) ) {
            $args['body'] = wp_json_encode( $body );
        }

        $response = wp_remote_request( $url, $args );

        if ( is_wp_error( $response ) ) {
            error_log( '[WooDoliSync] HTTP error ' . $method . ' ' . $endpoint . ': ' . $response->get_error_message() );
            return $response;
        }

        $code = wp_remote_retrieve_response_code( $response );
        $raw  = wp_remote_retrieve_body( $response );

        if ( $code >= 400 ) {
            $masked_token = strlen( $this->token ) > 32
                ? substr( $this->token, 0, strlen( $this->token ) - 32 ) . str_repeat( '*', 32 )
                : str_repeat( '*', strlen( $this->token ) );

            error_log( sprintf(
                '[WooDoliSync] Dolibarr %s %s HTTP %d — token: %s — body: %s',
                $method,
                $endpoint,
                $code,
                $masked_token,
                substr( $raw, 0, 300 )
            ) );

            return new WP_Error(
                'dolibarr_api_error',
                sprintf( 'Dolibarr %s %s returned HTTP %d', $method, $endpoint, $code ),
                [ 'status' => $code, 'body' => $raw ]
            );
        }

        $decoded = json_decode( $raw, true );
        if ( JSON_ERROR_NONE !== json_last_error() ) {
            return new WP_Error( 'dolibarr_json_error', 'Invalid JSON from Dolibarr', [ 'raw' => $raw ] );
        }

        return $decoded;
    }
}
