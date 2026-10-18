# Python and Notebook entry points

After the explicit noneditable installation, use [installed_simulation.py](../examples/installed_simulation.py), [calculation Notebook](../examples/notebook_single_sim.ipynb), or [offline postprocessing Notebook](../examples/notebook_skyrmion_postprocess.ipynb). Root my_case files are small public templates, not private research inputs.

Run the Python example from a fresh working directory with the environment's interpreter:

```sh
mkdir -p runs
simulation_work_dir=$(mktemp -d "$PWD/runs/run-XXXXXX")
cd "$simulation_work_dir"
conda run --name micromagnetics python -I /absolute/path/to/repository/examples/installed_simulation.py
```

Replace the example script path before executing. Default output is current-directory/results/notebook_demo, with prepare/static/drive output families. Reusing owned output names requires typing OVERWRITE; other answers cancel before calculation. Foreign/modified files are refused. Prefer a new directory.

In VS Code, open a tutorial and choose **Python (micromagnetics)**, or explicitly select the new Conda environment's bin/python. Do not add checkout paths to sys.path or use Notebook installation cells. Check Path.cwd() and set output_dir to a new destination before running calculations. Existing simulated objects continue when run/relax is called; constructing a new object restarts its initial state.

The postprocessing Notebook has generate_example=False and run_analysis=False by default: it neither reads user states nor computes fields. Enable only the operation you choose, with explicit input and a new CSV path. The analytic example creates a unique synthetic directory and uses native Notebook SVG output; no browser or matplotlib dependency is required. The small calculation example is not a general accuracy guarantee.

See [parameters](interface-v01/PARAMETERS.md), [output semantics](interface-v01/NOTEBOOK_OUTPUTS.md), [state continuity](interface-v01/STATE_AND_CONTINUITY.md), [postprocessing](interface-v01/SKYRMION_POSTPROCESSING.md), and [accepted scope](ACCEPTANCE_SUMMARY.md).
