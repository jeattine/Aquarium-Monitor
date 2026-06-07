# Define source and destination paths
$sourceFile1 = "C:\Users\johna\Dropbox\GitHub\Aquarium-Monitor\aquamon.py"
$destinationFolder1 = "C:\Users\johna\Dropbox\ReefMonitor\"
$sourceFile2 = "C:\Users\johna\Dropbox\GitHub\Aquarium-Monitor\config.txt"
$destinationFolder2 = "C:\Users\johna\Dropbox\ReefMonitor\"


# Define the prompt message and choices
$title   = "File Staging Confirmation"
$message1 = "Copy aquamon.py from GitHub\Aquarium-Monitor\ to ReefMonitor\"
$message2 = "Copy config.txt from GitHub\Aquarium-Monitor\ to ReefMonitor\"

$choices = [System.Management.Automation.Host.ChoiceDescription[]] @(
    New-Object System.Management.Automation.Host.ChoiceDescription "&Yes", "Copies the file to the destination."
    New-Object System.Management.Automation.Host.ChoiceDescription "&No", "Cancels the file copy operation."
)

# The third argument (0) sets 'Yes' as the default choice if the user just hits Enter
$decision = $Host.UI.PromptForChoice($title, $message1, $choices, 0)

# Process the user's decision
# 0 = Yes, 1 = No (based on the array order above)
if ($decision -eq 0) {
    Write-Host "Copying file..." -ForegroundColor Green

    # Check if the source file actually exists before copying
    if (Test-Path $sourceFile1) {
        # Ensure destination folder exists, then copy
        if (!(Test-Path $destinationFolder1)) {
            New-Item -ItemType Directory -Path $destinationFolder1 | Out-Null
        }
        Copy-Item -Path $sourceFile1 -Destination $destinationFolder1 -Force
        Write-Host "File successfully copied!" -ForegroundColor Green
    } else {
        Write-Warning "Source file not found at: $sourceFile1"
    }
}
 else {
    Write-Host "Skip staging of aquamon.py" -ForegroundColor Yellow
}

$decision = $Host.UI.PromptForChoice($title, $message2, $choices, 0)

# Process the user's decision
# 0 = Yes, 1 = No (based on the array order above)
if ($decision -eq 0) {
    Write-Host "Copying file..." -ForegroundColor Green

    # Check if the source file actually exists before copying
    if (Test-Path $sourceFile2) {
        # Ensure destination folder exists, then copy
        if (!(Test-Path $destinationFolder2)) {
            New-Item -ItemType Directory -Path $destinationFolder2 | Out-Null
        }
        Copy-Item -Path $sourceFile2 -Destination $destinationFolder2 -Force
        Write-Host "File successfully copied!" -ForegroundColor Green
    } else {
        Write-Warning "Source file not found at: $sourceFile2"
    }
}
 else {
    Write-Host "Skip staging of config.txt" -ForegroundColor Yellow
}

