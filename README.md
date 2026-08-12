# finance-tracker-azure

## Current Status

Complete as of August 2026. See post build section below for details on how to deploy.

## Disclaimer

This is a personal portfolio project created for learning and demonstration purposes.  

Use at your own risk. I accept no responsibility for any costs, data loss, or issues that may arise from deploying or using this code. Always review the code and understand what it will create, or delete before deploying to a real Azure subscription.

## Pre-Build

**My background**

I have been an RPA Developer for the last 10 years, working in the Insurance, Energy and Charity sectors. It is my intention to pivot career paths and transition into an Azure based role.

With this in mind, I have been actively learning Azure and I formally achieved my AZ-104 certification in June 2026. I detailed my learning journey in a repo that can be viewed [here](https://github.com/ricky-strapp/AZ-104-Study). This is an additional project to allow me to practice and demonstrate my Azure proficiency in a more complete way.

**Initial concept**

I have a personal app which I use to help me track my finances. For full disclosure, I built this application with Claude. I directed the design, specified the features, and tested it throughout, with Claude handling most of the implementation. It's a locally hosted Python/SQLite/Flask app which is both fully functional and stable; I use the app on a daily basis.

My intention is to move the app to be hosted on Azure, primarily to demonstrate genuine Azure administration and cloud engineering skills, including infrastructure-as-code, CI/CD automation, identity-based security, and proper operational practices (monitoring, logging, alerting, backup, cost control).

The application itself is just the vehicle here. The point is everything built around it.

The fact that this is a real useful app, that does contain my personal data means it adds a more realistic element to this project as I will have to demonstrate production level Azure skills that are applicable in a standard business environment (safety and security for example).

**Architecture**

I wish to keep the underlying app code essentially unchanged throughout the process.

As a basic level, I wish for there to be two environments (a personal one for my data, and a second demo one seeded with fake data). The end goal is to have the entire project as IaC. This will allow me to easily tear the app down and revert back to local hosting when the project is complete, or equally re-host it again if the need arises.

Cost is an element here that I will be considering as this is a personal project and I do want to keep costs reasonable.

For the compute element, I have considered various options but ultimately settled on Azure Container Apps. I picked this because it can scale down to zero instances when I am not using it, which is important given the low usage the app has and the cost restrictions. Azure Web Apps may have been the better technical solution, however I ruled it out on cost (I would need the Basic plan for what I want to achieve which is unnecessary here).

The database needs to remain on SQLite to avoid larger database related code changes in the app, so for that reason my intention is to use an Azure File Share mounted to the app to store the database.

It is my intention to also use other various elements in Azure during this project such as Entra ID, Networking elements, Key Vault, Azure Policy, Azure Monitor, Backup facilities and also Bicep and GitHub Actions as well.

## Post-Build

**Architecture Summary**

- Two environments: Personal and Demo
- Azure Container Apps with scale-to-zero for cost efficiency.
- Azure Files mount used for SQLite database persistence on the personal environment.
- Entra ID access only on the personal environment
- Full Infrastructure as Code using Bicep.
- CI/CD via GitHub Actions.
- Supporting services: Key Vault, Log Analytics, Recovery Services Vault, alerts, and budgets.

**How to deploy**

Prerequisites:
- Azure CLI installed and logged in
- GitHub account
- Contributor (or Owner) access on an Azure subscription

1. Clone repo using the following command:
```
git clone https://github.com/ricky-strapp/finance-tracker-azure.git
cd finance-tracker-azure
```
2. Open infra/main.bicepparam and update:

`location` (default is ukwest)

`alertEmail` (use a real email if you want notifications)

3. Deploy the infrastructure using the following CLI command:
```
az deployment sub create \
  --location ukwest \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam
```
Note: The first deployment uses the Microsoft Hello World image because the Container Registry starts empty. GitHub Actions will later replace it with your real application image.

4. Manual Post-Deployment Steps

*A: Grant yourself the 'Key Vault Secrets Officer' role*
- Go to the Azure Portal and open the Key Vault (kv-fintrack-personal).
- In the left menu, click Access control (IAM).
- Click + Add → Add role assignment.
- On the Role tab, search for and select Key Vault Secrets Officer.
- Click Next.
- On the Members tab, click + Select members.
- Search for your own user account, select it, then click Select.
- Click Review + assign, then Review + assign again to confirm.

*B: Configure Microsoft Entra ID (Easy Auth) on the Personal Container App*
- Go to the Azure Portal → Container Apps → as-fintrack-personal-ukwest (or your deployment location as appropriate)
- Select Authentication in the left menu
- Click Add identity provider
- Choose Microsoft
- Configure:App registration type: Create new app registration (or use existing)
- Restrict access to: Specific users/groups → select only yourself
- Save the settings

5. In your GitHub repository go to Settings → Secrets and variables → Actions and add the following secrets:

| Secret Name             | Where/How to obtain value |
|-------------------------|---------------------------|
| `AZURE_CLIENT_ID`       | Client ID of `gh-fintrack-identity` (can be found in Azure Portal → Managed Identities → select gh-fintrack-identity) |
| `AZURE_TENANT_ID`       | Your Azure Tenant ID - `az account show --query tenantId -o tsv` |
| `AZURE_SUBSCRIPTION_ID` | Your Azure Subscription ID - `az account show --query id -o tsv` | 
6. Deploy the real application image
- Push any change to the main branch of the repo and Github Actions will build the docker image, push it to the container registry and update both apps.
7. Access the Applications
- Demo will be publicly accessible
- Personal will be restricted via Entra ID, but does have persistent storage so can be used long term if required.
8. Tear-down (if required)
- Run ./scripts/teardown.ps1
- This powershell script will cleanly stop any Backup protection, delete the subscription level budget, deletes all applicable resource groups and purges any soft-deleted key vaults.

**Build notes**

[Click here](Build%20Notes.md)

**Lessons learned**

In general this project has been well worth doing. I have learnt a considerable amount about how a more realistic project would work in Azure. There are a lot of similarities with how I structured my RPA builds, but some key differences as well. In no particular order, some of the key issues were:
- Race conditions are a factor to consider (even with using dependsOn, timing issues cropped up regularly)
- Scoping correctly is challenging
- Soft deletion of resources like key vaults (this limits flexibility in testing for example)
- SQLite doesn't mix well with SMB File Share (this was expected, and while painful, was still less painful than extensive rewriting the application which was outside of the scope of the project)
- Getting used to the declarative nature of bicep. I have worked SQL in the past, so this is not unfamiliar to me, but still requires a deliberate shift in thinking style.
