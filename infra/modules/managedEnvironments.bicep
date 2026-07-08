targetScope = 'resourceGroup'

param managedEnvironmentName string
param workspaceCustomerId string
param workspaceName string
param workspaceRgName string

resource existingWorkspace 'Microsoft.OperationalInsights/workspaces@2025-07-01' existing = {
  name: workspaceName
  scope: resourceGroup(workspaceRgName)
}

resource managedEnvironment 'Microsoft.App/managedEnvironments@2025-07-01' = {
  name: managedEnvironmentName
  location: resourceGroup().location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspaceCustomerId
        sharedKey: existingWorkspace.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {}
  }
}
