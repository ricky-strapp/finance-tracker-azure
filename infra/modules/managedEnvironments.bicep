targetScope = 'resourceGroup'

param managedEnvironmentName string
param workspaceCustomerId string
param workspaceName string
param workspaceRgName string
param subnetResourceId string

resource existingWorkspace 'Microsoft.OperationalInsights/workspaces@2025-07-01' existing = {
  name: workspaceName
  scope: resourceGroup(workspaceRgName)
}

resource managedEnvironment 'Microsoft.App/managedEnvironments@2025-07-01' = {
  name: managedEnvironmentName
  location: resourceGroup().location
  properties: {
    infrastructureResourceGroup: '${resourceGroup().name}-infra'
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspaceCustomerId
        sharedKey: existingWorkspace.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: subnetResourceId
      internal: false
    }
  }
}

output managedEnvironmentId string = managedEnvironment.id
output managedEnvironmentName string = managedEnvironment.name
