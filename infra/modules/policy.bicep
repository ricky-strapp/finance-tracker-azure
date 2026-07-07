targetScope = 'resourceGroup'

var inheritTagfromRGGUID = '/providers/Microsoft.Authorization/policyDefinitions/cd3aa116-8754-49c9-a813-ad46512ece54'

resource inheritEnvironmentTagfromRG 'Microsoft.Authorization/policyAssignments@2020-09-01' = {
  name: 'inheritEnvironmentTagfromRG'
  location: resourceGroup().location
  properties: {
    displayName: 'Inherit Environment Tag from Resource Group'
    description: 'This policy automatically inherits environment tags from the resource group to the resources created within it.'
    policyDefinitionId: inheritTagfromRGGUID
    parameters:{
      tagName: {
        value: 'Environment'
      }
    }
  }
  identity: {
    type: 'SystemAssigned'
    }
}

resource inheritProjectTagfromRG 'Microsoft.Authorization/policyAssignments@2020-09-01' = {
  name: 'inheritProjectTagfromRG'
  location: resourceGroup().location
  properties: {
    displayName: 'Inherit Project Tag from Resource Group'
    description: 'This policy automatically inherits project tags from the resource group to the resources created within it.'
    policyDefinitionId: inheritTagfromRGGUID
    parameters:{
        tagName: {
          value: 'Project'
        }
      }
  }
  identity: {
    type: 'SystemAssigned'
    }
} 
