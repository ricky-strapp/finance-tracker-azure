# finance-tracker-azure

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