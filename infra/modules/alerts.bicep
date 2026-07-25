targetScope = 'resourceGroup'

param location string 
param actionGroupName string
param alertEmail string
param metricAlertName string
param groupShortName string
param containerAppsResourceId string

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: actionGroupName
  location: location
  properties: {
    emailReceivers: [
      {
      name: 'Email Alert'
      emailAddress: alertEmail 
      useCommonAlertSchema: true
      }
    ]
  enabled: true 
  groupShortName: groupShortName
  }
}

resource metricAlert 'Microsoft.Insights/metricAlerts@2026-01-01' = {
  name: metricAlertName
  location: 'global'
  properties: {
    description: 'Alerts if the personal container app restarts repeatedly'
    targetResourceType: 'Microsoft.App/containerApps'
    enabled: true
    severity: 2
    scopes: [
      containerAppsResourceId
    ]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT30M'
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [{
        name: 'RestartCount'
        metricName: 'RestartCount'
        metricNamespace: 'Microsoft.App/containerapps'
        criterionType: 'StaticThresholdCriterion'
        operator: 'GreaterThan'
        threshold: 3
        timeAggregation: 'Maximum'
        }]
      }
    actions: [{
        actionGroupId: actionGroup.id
        }
      ]
  }
}
