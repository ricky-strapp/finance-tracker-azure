targetScope = 'resourceGroup'

param resourceName string
param location string
param principalId string

resource vault 'Microsoft.KeyVault/vaults@2021-10-01' = {
  name: resourceName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: tenant().tenantId
    enableRbacAuthorization: true
  }
}

resource addRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, 'fintrack-identity', 'roleAssignment')
  scope: vault
    properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}
