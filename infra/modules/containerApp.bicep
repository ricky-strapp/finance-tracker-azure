targetScope = 'resourceGroup'

param resourceName string
param location string 
param managedEnvironmentId string
param identityID string
param containerRegistryName string
param containerImage string
param volumes array
param volumeMounts array


resource containerApp 'Microsoft.App/containerApps@2026-01-01' = {
  name: resourceName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {'${identityID}':{}}
    }
  properties: {
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
            external: true
            targetPort: 5000
            transport: 'auto'
      } 
      registries: [
        {
          identity: identityID
          server: containerRegistryName
        }]
    }
    environmentId: managedEnvironmentId
    template: {
      containers: [
        {
          env: []
          image: containerImage
          name: 'fintrack'
          probes: []
          resources: {
            cpu: any('0.25')
            memory: '0.5Gi'
          }
          volumeMounts: volumeMounts
        }
      ]
      scale: {
        maxReplicas: 10
      }
      volumes: volumes
    }
  }
}
