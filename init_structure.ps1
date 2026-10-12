$directories = @(
    "src/reconstruction",
    "src/mesh_preprocessing",
    "src/cadfit_wrapper",
    "src/cad_ir",
    "src/engineering_agent",
    "src/solidworks_adapter",
    "src/validation",
    "src/mold_design/draft_analysis",
    "src/mold_design/parting_line",
    "src/mold_design/core_cavity",
    "demo_part/input/images",
    "demo_part/input/scan",
    "demo_part/input/drawing",
    "demo_part/reconstruction",
    "demo_part/cadfit",
    "demo_part/cad_ir",
    "demo_part/solidworks",
    "demo_part/validation",
    "demo_part/mold/draft_analysis",
    "demo_part/mold/parting_line",
    "demo_part/mold/core",
    "demo_part/mold/cavity",
    "ground_truth",
    "docs",
    "tests"
)

foreach ($dir in $directories) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

New-Item -ItemType File -Force -Path "demo_part/input/description.txt" | Out-Null
New-Item -ItemType File -Force -Path "ground_truth/specification.json" | Out-Null
New-Item -ItemType File -Force -Path "src/main.py" | Out-Null
New-Item -ItemType File -Force -Path "requirements.txt" | Out-Null
New-Item -ItemType File -Force -Path "README.md" | Out-Null

Write-Host "Directory structure created successfully!"
