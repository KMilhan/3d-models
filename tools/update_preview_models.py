from __future__ import annotations

import json
from pathlib import Path

NOTEBOOK_PATH = Path(__file__).resolve().parents[1] / "notebooks" / "preview_models.ipynb"

notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))

notebook["cells"][1]["source"] = [
    "from pathlib import Path\n",
    "\n",
    "from jupyter_cadquery import show\n",
    "\n",
    "from build123d import import_step\n",
]

notebook["cells"][3]["source"] = [
    "# 모델 탐색 및 로드\n",
    'models_dir = Path("../models")\n',
    'step_files = list(models_dir.rglob("*.step"))\n',
    "\n",
    "loaded_models = {}\n",
    "for f in step_files:\n",
    '    print(f"Loading {f.name}...")\n',
    "    try:\n",
    "        model = import_step(str(f))\n",
    "        loaded_models[f.stem] = model\n",
    "    except Exception as error:\n",
    '        print(f"Failed to load {f.name}: {error}")\n',
    "\n",
    'print(f"\\n총 {len(loaded_models)}개의 모델을 로드했습니다.")\n',
]

notebook["cells"][4]["source"] = [
    "# 모든 모델을 순차적으로 보여주기\n",
    "if loaded_models:\n",
    "    for name, model in loaded_models.items():\n",
    '        print(f"\\n--- {name} ---")\n',
    "        show(model)\n",
    "else:\n",
    '    print("표시할 모델이 없습니다.")\n',
]

notebook["cells"][6]["source"] = [
    "if loaded_models:\n",
    "    first_model_name = next(iter(loaded_models))\n",
    '    print(f"Showing {first_model_name}...")\n',
    "    show(loaded_models[first_model_name])\n",
]

NOTEBOOK_PATH.write_text(
    json.dumps(notebook, ensure_ascii=False, indent=1),
    encoding="utf-8",
)
