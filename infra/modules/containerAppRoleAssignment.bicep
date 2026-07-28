targetScope = 'resourceGroup'

param githubIdentityId string
param appName string

resource targetContainerApp 'Microsoft.App/containerApps@2024-03-01' existing = {
  name: appName
}

resource roleAssignmentContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(targetContainerApp.id, githubIdentityId, 'roleAssignmentContributor')
  scope: targetContainerApp
  properties: {
    description: 'Role assignment for user-assigned managed identity as Container Apps Contributor'
    principalId: githubIdentityId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '358470bc-b998-42bd-ab17-a7e34c199c0f')
  }
}
