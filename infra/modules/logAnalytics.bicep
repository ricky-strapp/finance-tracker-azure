targetScope = 'resourceGroup'

param workspaceName string
param workspaceSku string

resource workspace 'Microsoft.OperationalInsights/workspaces@2025-07-01' = {
  name: workspaceName
  location: resourceGroup().location
  properties: {
    features: {
      disableLocalAuth: false
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
    retentionInDays: 30
    sku: {
      name: workspaceSku
    }
    workspaceCapping: {
      dailyQuotaGb: 1
    }
  }
}
