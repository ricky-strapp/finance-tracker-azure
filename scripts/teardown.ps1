# teardown.ps1
# Tears down the fintrack environment for cost control between work sessions.
#
# WHAT THIS DOES, IN ORDER (order matters - see Phase 6 notes on why):
#   1. Stops backup protection and deletes backup data on the personal vault
#   2. Deletes the subscription-level budget
#   3. Deletes all three resource groups, and WAITS until they're actually gone
#   4. Purges every soft-deleted Key Vault in the subscription
#
# WHAT THIS DOES NOT DO: rebuild anything. See the message at the end.

param(
    [string]$Location = "ukwest",
    [string]$BudgetName = "fintrack-monthly-budget",
    [string]$VaultName = ""
)

$personalRG = "rg-fintrack-personal-$Location"
$demoRG     = "rg-fintrack-demo-$Location"
$sharedRG   = "rg-fintrack-shared-$Location"
$vaultName  = if ($VaultName) { $VaultName } else { "rsv-fintrack-personal-$Location" }

# Confirm Azure CLI is actually logged in before doing anything destructive.
az account show --output none 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Not logged into Azure CLI. Run 'az login' first." -ForegroundColor Red
    exit 1
}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "     FINTRACK ENVIRONMENT TEARDOWN & PURGE        " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "This will PERMANENTLY DELETE:" -ForegroundColor Yellow
Write-Host "  $personalRG (includes your real data's storage/backup)" -ForegroundColor Yellow
Write-Host "  $demoRG"
Write-Host "  $sharedRG"
Write-Host "  Budget: $BudgetName"
$confirm = Read-Host "Type DELETE to confirm"
if ($confirm -ne "DELETE") {
    Write-Host "Aborted. Nothing was touched." -ForegroundColor Red
    exit 0
}

# --- Step 1: Backup protection MUST be stopped before the resource group is
# deleted, or deletion can silently hang - this is the step last run skipped. ---
Write-Host "`n[1/4] Stopping backup protection on the personal vault..." -ForegroundColor Cyan
az backup vault show --name $vaultName --resource-group $personalRG --output none 2>$null
if ($LASTEXITCODE -eq 0) {
    $items = az backup item list --resource-group $personalRG --vault-name $vaultName --output json 2>$null | ConvertFrom-Json
    if ($items -and $items.value) {
        foreach ($item in $items.value) {
            $containerName = $item.properties.containerName
            $itemName = $item.name
            Write-Host "  Stopping protection for $itemName..."
            az backup protection disable --resource-group $personalRG --vault-name $vaultName --container-name $containerName --item-name $itemName --delete-backup-data true --yes
        }
    } else {
        Write-Host "  Vault exists but has no protected items - continuing."
    }
} else {
    Write-Host "  No vault named '$vaultName' found in $personalRG - skipping."
    Write-Host "  (If unexpected, check: az resource list --resource-type Microsoft.RecoveryServices/vaults -o table)"
}

# --- Step 2: Budget (subscription-scoped, not inside any resource group) ---
Write-Host "`n[2/4] Removing subscription-level budget..." -ForegroundColor Cyan
$budgetExists = az consumption budget list --query "[?name=='$BudgetName'].name" -o tsv 2>$null
if ($budgetExists) {
    az consumption budget delete --budget-name $BudgetName
    Write-Host "  Budget deleted." -ForegroundColor Green
} else {
    Write-Host "  Budget '$BudgetName' already clean or not found." -ForegroundColor DarkGray
}

# --- Step 3: Resource groups - triggered together, then actually waited for ---
Write-Host "`n[3/4] Deleting resource groups..." -ForegroundColor Cyan
$resourceGroups = @($personalRG, $demoRG, $sharedRG)
foreach ($rg in $resourceGroups) {
    Write-Host "  Triggering deletion for: $rg"
    az group delete --name $rg --yes --no-wait
}

Write-Host "  Waiting for deletion to finish (this genuinely takes several minutes)..."
do {
    Start-Sleep -Seconds 30
    $stillThere = $resourceGroups | Where-Object { (az group exists --name $_) -eq "true" }
    if ($stillThere) {
        Write-Host "    Still deleting: $($stillThere -join ', ')"
    }
} while ($stillThere)
Write-Host "  All resource groups confirmed deleted." -ForegroundColor Green

# --- Step 4: Purge every soft-deleted Key Vault (Gemini's list-based approach -
# more robust than guessing one name, since names have changed before) ---
Write-Host "`n[4/4] Purging soft-deleted Key Vaults..." -ForegroundColor Cyan
$deletedVaults = az keyvault list-deleted --query "[].name" -o tsv 2>$null
if ($deletedVaults) {
    foreach ($vault in $deletedVaults) {
        Write-Host "  Purging: $vault"
        az keyvault purge --name $vault --location $Location 2>$null
    }
} else {
    Write-Host "  No soft-deleted Key Vaults found." -ForegroundColor DarkGray
}

Write-Host "`n==================================================" -ForegroundColor Cyan
Write-Host " Teardown complete - confirmed, not just triggered." -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "To rebuild:"
Write-Host "  az deployment sub create --location $Location --template-file infra/main.bicep --parameters infra/main.bicepparam"
Write-Host "Then: re-run the GitHub Actions workflow for the image, redo Easy Auth, re-enable backup protection, re-upload real data."
