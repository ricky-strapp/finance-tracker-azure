targetScope = 'resourceGroup'

module personalPolicy './modules/policy.bicep' = {
  name: 'personal-policy'
  scope: resourceGroup('rg-fintrack-personal-uksouth')
  params: {
    environmentTagValue: 'Personal'
  }
}

module sharedPolicy './modules/policy.bicep' = {
  name: 'shared-policy'
  scope: resourceGroup('rg-fintrack-shared-uksouth')
  params: {
    environmentTagValue: 'Shared'
  }
}
