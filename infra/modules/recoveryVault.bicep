targetScope = 'resourceGroup'

param resourceName string
param location string 
param policyName string

resource recoveryVault 'Microsoft.RecoveryServices/vaults@2026-05-01' = {
  name: resourceName
  location: location
  sku: {
    name: 'RS0'
    tier: 'Standard'
  }
  properties: {
    publicNetworkAccess: 'Enabled'
  }
}

resource backupPolicy 'Microsoft.RecoveryServices/vaults/backupPolicies@2026-05-01' = {
  name: policyName
  parent: recoveryVault
  properties: {
    backupManagementType: 'AzureStorage'
    retentionPolicy: {
      dailySchedule: {
        retentionTimes: [
          '2026-01-01T02:00:00Z'
        ]
        retentionDuration: {
          count: 30
          durationType: 'Days'
        }
      }
      retentionPolicyType: 'LongTermRetentionPolicy'
    }
    schedulePolicy: {
      schedulePolicyType: 'SimpleSchedulePolicy'
      scheduleRunFrequency: 'Daily'
      scheduleRunTimes: [
        '2026-01-01T02:00:00Z'
      ]
    }
    timeZone: 'UTC'
    workLoadType: 'AzureFileShare'
  }
}
