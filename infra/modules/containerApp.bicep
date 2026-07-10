targetScope = 'resourceGroup'

param resourceName string
param location string 
param managedEnvironmentId string

resource containerApp 'Microsoft.App/containerApps@2026-01-01' = {
  name: resourceName
  location: location
  properties: {
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
            external: true
            targetPort: 80
            transport: 'auto'
      } 
    }
    environmentId: managedEnvironmentId
    template: {
      containers: [
        {
          env: []
          image: 'mcr.microsoft.com/k8se/quickstart:latest'
          name: 'testimage'
          probes: []
          resources: {
            cpu: any('0.25')
            memory: '0.5Gi'
          }
          volumeMounts: []
        }
      ]
      scale: {
        maxReplicas: 10
      }
      volumes: []
    }
  }
}
