Build Notes

## 07/072026
- Amended the bicep files to create tagging policy, to use a main.bicep file which can pass through parameters instead. However I then realised that this is also not quite how I would need it to be because the policy creation is dependant on resource groups already existing. They exist now in the portal, but when I tear down everything, they won't exist any more and the deployment will fail. I need to have a module for RG creation that can be called on but it needs to be scoped to a higher level than resource group.

## 04/07/2026
- Created two bicep files for tagging policy, one for each half of the project. However I quickly realised that that having individual bicep files for everything is going to get hard to manage and deploy easily, so I also did a bit of research about how bicep files are typically managed.
- In my next session I will create a main bicep file that will call the others. I'll need to amend the files that I've already made as well to fit in with that decision.

## 03/07/2026
- Created repo. 
- Created readme file - detailing what my initial build thoughts are and what I hope to achieve. 
