import Keycloak from 'keycloak-js'

const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_PUBLIC_URL || 'MISSING_KEYCLOAK_URL',
  realm: import.meta.env.VITE_KEYCLOAK_REALM || 'MISSING_KEYCLOAK_REALM',
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'MISSING_KEYCLOAK_CLIENT_ID',
})

const initKeycloak = async () => {
  try {
    const authenticated = await keycloak.init({
      onLoad: 'login-required',
      checkLoginIframe: false,
    })
    return { keycloak, isAuthenticated: authenticated }
  } catch (error) {
    console.error('Keycloak init failed:', error)
    return { keycloak, isAuthenticated: false }
  }
}

export { keycloak, initKeycloak }
