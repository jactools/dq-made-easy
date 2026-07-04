# frozen_string_literal: true

require 'uri'
require 'net/http'
require 'json'

server_side_url = ENV.fetch('KEYCLOAK_SERVER_SIDE_URL').to_s.strip
raise 'KEYCLOAK_SERVER_SIDE_URL is required' if server_side_url.empty?

require 'openid_connect'
require 'omni_auth/strategies/oidc_database'

# Zammad should discover Keycloak over HTTPS through the host-published issuer
# that is reachable from the container.
OpenIDConnect.validate_discovery_issuer = false

# The bundled Zammad login shell starts the OpenID Connect flow with a POST,
# and in this container the request-phase CSRF token is not forwarded by that UI.
OmniAuth.config.request_validation_phase = nil

def zammad_public_url
  http_type = Setting.get('http_type').to_s.strip
  fqdn = Setting.get('fqdn').to_s.strip
  if http_type.present? && fqdn.present?
    "#{http_type}://#{fqdn}"
  else
    ENV.fetch('ZAMMAD_PUBLIC_URL').to_s.strip
  end
end

OmniAuth.config.full_host = proc { zammad_public_url.chomp('/') }

module ZammadOpenIdConnectCallbackUrl
  def setup
    config = super
    client_options = config.fetch(:client_options, {})

    config.merge(
      client_options: client_options.merge(
        redirect_uri: "#{zammad_public_url.chomp('/')}/auth/openid_connect/callback",
      ),
    )
  end
end

OmniAuth::Strategies::OidcDatabase.singleton_class.prepend(ZammadOpenIdConnectCallbackUrl)

module ZammadOpenIdConnectUserInfoFallback
  def user_info
    super
  rescue OpenIDConnect::Unauthorized
    decoded = decode_id_token(access_token.id_token).raw_attributes
    ::OpenIDConnect::ResponseObject::UserInfo.new(decoded)
  end
end

OmniAuth::Strategies::OidcDatabase.prepend(ZammadOpenIdConnectUserInfoFallback)

class << OpenIDConnect::Discovery::Provider::Config
  def discover!(identifier, cache_options = {})
    server_side_base = URI.parse(ENV.fetch('KEYCLOAK_SERVER_SIDE_URL'))
    public_identifier = URI.parse(identifier)
    server_side_identifier = public_identifier.dup
    server_side_identifier.scheme = server_side_base.scheme
    server_side_identifier.host = server_side_base.host
    server_side_identifier.port = server_side_base.port

    discovery_uri = URI.parse(
      "#{server_side_identifier.scheme}://#{server_side_identifier.host}:#{server_side_identifier.port}#{File.join(server_side_identifier.path, '.well-known/openid-configuration')}",
    )

    http = Net::HTTP.new(discovery_uri.host, discovery_uri.port)
    http.use_ssl = discovery_uri.scheme == 'https'
    http.open_timeout = 5
    http.read_timeout = 10

    response_body = http.start { |client| client.get(discovery_uri.request_uri) }
    unless response_body.is_a?(Net::HTTPSuccess)
      raise OpenIDConnect::Discovery::DiscoveryFailed.new("Unexpected discovery response #{response_body.code}")
    end

    response_data = JSON.parse(response_body.body).transform_keys(&:to_sym)
    response = OpenIDConnect::Discovery::Provider::Config::Response.new(response_data)
    public_auth_endpoint = "#{identifier.to_s.chomp('/')}/protocol/openid-connect/auth"
    public_logout_endpoint = "#{identifier.to_s.chomp('/')}/protocol/openid-connect/logout"

    %i[
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
    ].each do |field|
      next unless response.respond_to?(field) && response.respond_to?("#{field}=")

      value = response.public_send(field)
      next if value.nil?

      rewritten = URI.parse(value)
      rewritten.scheme = server_side_base.scheme
      rewritten.host = server_side_base.host
      rewritten.port = server_side_base.port
      response.public_send("#{field}=", rewritten.to_s)
    end

    response.authorization_endpoint = public_auth_endpoint if response.respond_to?(:authorization_endpoint=)
    response.end_session_endpoint = public_logout_endpoint if response.respond_to?(:end_session_endpoint=)

    response
  end
end