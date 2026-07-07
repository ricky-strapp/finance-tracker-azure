using 'main.bicep'

param rgDetails = [
  {
    rgName: 'rg-fintrack-personal-uksouth'
    rgEnvironment: 'Personal'
    rgProject: 'Finance-Tracker'
  }
  {
    rgName: 'rg-fintrack-shared-uksouth'
    rgEnvironment: 'Shared'
    rgProject: 'Finance-Tracker'
  }
  {
    rgName: 'rg-fintrack-demo-uksouth'
    rgEnvironment: 'Demo'
    rgProject: 'Finance-Tracker'
  }
]
