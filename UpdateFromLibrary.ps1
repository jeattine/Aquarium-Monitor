# Define source and destination paths
$file1 = "aquamon.py"
$sourceFile1 = "C:\Users\johna\Dropbox\GitHub\Aquarium-Monitor\${file1}"
$destinationFolder1 = "C:\Users\johna\Dropbox\ReefMonitor\"
$file2 = "config.txt"
$sourceFile2 = "C:\Users\johna\Dropbox\GitHub\Aquarium-Monitor\${file2}"
$destinationFolder2 = "C:\Users\johna\Dropbox\ReefMonitor\"


# Define the prompt message and choices
$title1   = "File ${file1} Staging Confirmation"
$title2   = "File ${file2} Staging Confirmation"
$message1 = "Copy ${sourceFile1} to ${destinationFolder1}"
$message2 = "Copy ${sourceFile2} to ${destinationFolder2}"

$choices = [System.Management.Automation.Host.ChoiceDescription[]] @(
    New-Object System.Management.Automation.Host.ChoiceDescription "&Yes", "Copies the file to the destination."
    New-Object System.Management.Automation.Host.ChoiceDescription "&No", "Cancels the file copy operation."
)

# The third argument (0) sets 'Yes' as the default choice if the user just hits Enter
$decision = $Host.UI.PromptForChoice($title1, $message1, $choices, 0)

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
        Write-Warning "Source file not found at: ${sourceFile1}"
    }
}
 else {
    Write-Host "Skip staging of ${file1}" -ForegroundColor Yellow
}

$decision = $Host.UI.PromptForChoice($title2, $message2, $choices, 0)

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
		$new_name = Read-Host "Enter your email address for sending alerts"
		Write-Host "You entered: ${new_name}"
		$content = Get-Content "${destinationFolder2}${file2}" -Raw
		# Detect original line ending
		$lineEnding = if ($content.Contains("`r`n")) { "`r`n" } else { "`n" }
		# Replace text
		$content = $content -replace 'email_recipients=', "email_recipients=${new_name}"
		# Normalize back to original line ending
		$content = $content -replace "`r`n|`n", $lineEnding
		# Write back
		[System.IO.File]::WriteAllText("${destinationFolder2}${file2}", $content)
		Write-Host "email name updated successfully"
    } else {
        Write-Warning "Source file not found at: ${sourceFile2}"
    }
}
 else {
    Write-Host "Skip staging of ${file2}" -ForegroundColor Yellow
}

