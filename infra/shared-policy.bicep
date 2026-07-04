targetScope = 'resourceGroup'

var addTagsOnRGGUID = '/providers/Microsoft.Authorization/policyDefinitions/d157c373-a6c4-483d-aaad-570756956268'
var inheritTagfromRGGUID = '/providers/Microsoft.Authorization/policyDefinitions/cd3aa116-8754-49c9-a813-ad46512ece54'

resource addEnvironmentTagsOnRG 'Microsoft.Authorization/policyAssignments@2020-09-01' = {
  name: 'addEnvironmentTagsOnRG'
  location: resourceGroup().location
  properties: {
    displayName: 'Add Environment Tags on Resource Group'
    description: 'This policy automatically adds environment tags to a resource group when it is created.'
    policyDefinitionId: addTagsOnRGGUID
    parameters:{
        tagName: {value: 'Environment'}
        tagValue: {value: 'Shared'}
        }
  }
  identity: {
    type: 'SystemAssigned'
    }
}

resource addProjectTagsOnRG 'Microsoft.Authorization/policyAssignments@2020-09-01' = {
  name: 'addProjectTagsOnRG'
  location: resourceGroup().location
  properties: {
    displayName: 'Add Project Tags on Resource Group'
    description: 'This policy automatically adds project tags to a resource group when it is created.'
    policyDefinitionId: addTagsOnRGGUID
    parameters:{
        tagName: {value: 'Project'}
        tagValue: {value: 'Finance-Tracker'}
        }
  }
  identity: {
    type: 'SystemAssigned'
    }
}

resource inheritEnvironmentTagfromRG 'Microsoft.Authorization/policyAssignments@2020-09-01' = {
  name: 'inheritEnvironmentTagfromRG'
  location: resourceGroup().location
  properties: {
    displayName: 'Inherit Environment Tag from Resource Group'
    description: 'This policy automatically inherits environment tags from the resource group to the resources created within it.'
    policyDefinitionId: inheritTagfromRGGUID
    parameters:{
        tagName: {value: 'Environment'}
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
        tagName: {value: 'Project'}
        }
  }
  identity: {
    type: 'SystemAssigned'
    }
} 
