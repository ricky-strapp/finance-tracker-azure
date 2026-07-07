Build Notes

## 07/07/2026
- Amended the bicep files to create tagging policy, to use a main.bicep file which can pass through parameters instead. However I then realised that this is also not quite how I would need it to be because the policy creation is dependent on resource groups already existing. They exist now in the portal, but when I tear down everything, they won't exist any more and the deployment will fail. I need to have a module for RG creation that can be called on but it needs to be scoped to a higher level than resource group.
- I have added a parameters file now to provide the array of required resource groups to create before the policy is created. I have a resourceGroups bicep file which has a singular action to create an RG using the incoming parameters, rather than any hardcoding. Then I had to tweak the policy bicep as well to get everything to link together. I realised that I could entirely delete the policy regarding setting tags at the RG level as they are being done by the bicep earlier.
- If did a what if deployment to see if it would work ok. That came back fine, but then the deployment actually failed because of timings. The fix was to add a 'dependsOn' into the policy module, so that ARM doesn't run the policy module before the relevant RG is created.
- Most of the difficulty today was just syntax related and trying to understand how reusability works in practice with Bicep. The syntax is a minor issue and one that will become natural over time with increased usage. The reusability (object based programming) is something I am very familiar with from RPA, but it slightly different using bicep files and VS code to do it. I am confident this easily reinforced with more practice.
- Sources: [Microsoft Learn - Bicep Documentation](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/)

## 04/07/2026
- Created two bicep files for tagging policy, one for each half of the project. However I quickly realised that that having individual bicep files for everything is going to get hard to manage and deploy easily, so I also did a bit of research about how bicep files are typically managed.
- In my next session I will create a main bicep file that will call the others. I'll need to amend the files that I've already made as well to fit in with that decision.

## 03/07/2026
- Created repo. 
- Created readme file - detailing what my initial build thoughts are and what I hope to achieve. 
