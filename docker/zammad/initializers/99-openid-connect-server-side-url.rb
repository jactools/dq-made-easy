# frozen_string_literal: true

require 'uri'

server_side_url = ENV.fetch('KEYCLOAK_SERVER_SIDE_URL').to_s.strip
raise 'KEYCLOAK_SERVER_SIDE_URL is required' if server_side_url.empty?

require 'openid_connect'
require 'omni_auth/strategies/oidc_database'

# Zammad should discover Keycloak over HTTPS, but it must exchange tokens and
# fetch JWKS/userinfo through the canonical server-side URL that is reachable from the container.
OpenIDConnect.validate_discovery_issuer = false

# The bundled Zammad login shell starts the OpenID Connect flow with a POST,
# and in this container the request-phase CSRF token is not forwarded by that UI.
OmniAuth.config.request_validation_phase = nil
OmniAuth.config.full_host = proc { ENV.fetch('ZAMMAD_PUBLIC_URL').to_s.strip.chomp('/') }

module ZammadOpenIdConnectCallbackUrl
  def setup
    config = super
    client_options = config.fetch(:client_options, {})

    config.merge(
      client_options: client_options.merge(
        redirect_uri: "#{ENV.fetch('ZAMMAD_PUBLIC_URL').to_s.strip.chomp('/')}/auth/openid_connect/callback",
      ),
    )
  end
end

OmniAuth::Strategies::OidcDatabase.singleton_class.prepend(ZammadOpenIdConnectCallbackUrl)

module ZammadOpenIdConnectServerSideUrl
  SERVER_SIDE_FIELDS = %i[
    token_endpoint
    jwks_uri
    userinfo_endpoint
    end_session_endpoint
    revocation_endpoint
    introspection_endpoint
    registration_endpoint
    device_authorization_endpoint
    backchannel_authentication_endpoint
    pushed_authorization_request_endpoint
  ].freeze

  def discover!(identifier, cache_options = {})
    server_side_base = URI.parse(ENV.fetch('KEYCLOAK_SERVER_SIDE_URL'))
    public_identifier = URI.parse(identifier)
    server_side_identifier = public_identifier.dup
    server_side_identifier.scheme = server_side_base.scheme
    server_side_identifier.host = server_side_base.host
    server_side_identifier.port = server_side_base.port

    response = super(server_side_identifier.to_s, cache_options)
    response.issuer = identifier if response.respond_to?(:issuer=)

    SERVER_SIDE_FIELDS.each do |field|
      next unless response.respond_to?(field) && response.respond_to?("#{field}=")

      value = response.public_send(field)
      next if value.nil?

      rewritten = URI.parse(value)
      rewritten.scheme = server_side_base.scheme
      rewritten.host = server_side_base.host
      rewritten.port = server_side_base.port
      response.public_send("#{field}=", rewritten.to_s)
    end

    response
  end
end

OpenIDConnect::Discovery::Provider::Config.singleton_class.prepend(ZammadOpenIdConnectServerSideUrl)