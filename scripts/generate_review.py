#!/usr/bin/env python3
"""生成跨平台的本地评审页面，默认隐藏候选版本身份。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

try:
    from .evaluation_common import load_json
except ImportError:
    from evaluation_common import load_json


TEXT_SUFFIXES = {".md", ".txt", ".json", ".csv", ".yaml", ".yml", ".html", ".css", ".py"}
IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}
MAX_PREVIEW_CHARS = 12000
MAX_EMBED_BYTES = 8 * 1024 * 1024


HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{color-scheme:light dark;font-family:ui-sans-serif,system-ui,sans-serif}body{max-width:1120px;margin:0 auto;padding:32px 20px;line-height:1.55}h1,h2,h3{line-height:1.2}.muted{opacity:.68}.eval{border-top:1px solid #8886;padding-top:24px;margin-top:32px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}.card{border:1px solid #8886;border-radius:12px;padding:16px}.badge{display:block;font-weight:700;margin-top:12px}img{display:block;max-width:100%;height:auto;border-radius:8px}pre{white-space:pre-wrap;overflow:auto;background:#8881;padding:12px;border-radius:8px}textarea{width:100%;min-height:100px;box-sizing:border-box}table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #8885;padding:8px;text-align:left}button{padding:10px 16px;border-radius:8px;border:1px solid #8888;cursor:pointer}.pass{color:#198754}.fail{color:#c43d3d}</style>
</head>
<body>
<h1 id="title"></h1>
<p class="muted">默认隐藏候选版本身份。先查看输出并填写反馈，再查看汇总；不要根据版本名称判断质量。</p>
<div id="content"></div>
<h2>对比结果</h2>
<div id="benchmark"></div>
<p><button id="export" type="button">导出 feedback.json</button> <span id="status" class="muted" aria-live="polite"></span></p>
<script id="review-data" type="application/json">__DATA__</script>
<script>
const data=JSON.parse(document.getElementById('review-data').textContent);
document.getElementById('title').textContent=data.title;
const storageKey='oil-skill-review:'+data.title;
let drafts={};let storageAvailable=true;try{drafts=JSON.parse(localStorage.getItem(storageKey)||'{}')}catch(_error){drafts={};storageAvailable=false}
const content=document.getElementById('content');
for(const item of data.evals){
  const section=document.createElement('section'); section.className='eval';
  const h=document.createElement('h2'); h.textContent=item.name; section.appendChild(h);
  const prompt=document.createElement('pre'); prompt.textContent=item.prompt; section.appendChild(prompt);
  const grid=document.createElement('div'); grid.className='grid';
  for(const run of item.runs){
    const card=document.createElement('article'); card.className='card';
    const title=document.createElement('h3'); title.textContent=run.candidate+' · 第 '+run.repetition+' 次'; card.appendChild(title);
    if(run.files.length===0){const p=document.createElement('p');p.className='muted';p.textContent='没有输出文件';card.appendChild(p)}
    for(const file of run.files){
      const label=document.createElement('p'); label.className='badge'; label.textContent=file.name+' · '+file.size+' bytes'; card.appendChild(label);
      if(file.data_url!==null){const img=document.createElement('img');img.src=file.data_url;img.alt=file.name;card.appendChild(img)}
      if(file.preview!==null){const pre=document.createElement('pre');pre.textContent=file.preview;card.appendChild(pre)}
    }
    if(run.grading.length){
      const ul=document.createElement('ul');
      for(const grade of run.grading){const li=document.createElement('li');li.className=grade.passed?'pass':'fail';li.textContent=(grade.passed?'通过：':'失败：')+grade.text+' — '+grade.evidence;ul.appendChild(li)}
      card.appendChild(ul);
    }
    const label=document.createElement('label'); label.className='badge'; label.htmlFor=run.candidate_id; label.textContent='反馈'; card.appendChild(label);
    const area=document.createElement('textarea'); area.id=run.candidate_id; area.dataset.candidateId=run.candidate_id; area.placeholder='记录可复用的反馈；没有问题可以留空'; area.value=drafts[run.candidate_id]||'';
    area.addEventListener('input',()=>{drafts[run.candidate_id]=area.value;try{localStorage.setItem(storageKey,JSON.stringify(drafts))}catch(_error){storageAvailable=false}}); card.appendChild(area);
    grid.appendChild(card);
  }
  section.appendChild(grid); content.appendChild(section);
}
const bench=document.getElementById('benchmark');
if(data.benchmark.length){
  const table=document.createElement('table');
  table.innerHTML='<thead><tr><th>候选</th><th>运行次数</th><th>通过率</th><th>秒</th><th>Token</th></tr></thead>';
  const body=document.createElement('tbody');
  for(const row of data.benchmark){const tr=document.createElement('tr');for(const value of [row.candidate,row.runs,row.pass_rate,row.duration,row.tokens]){const td=document.createElement('td');td.textContent=value;tr.appendChild(td)}body.appendChild(tr)}
  table.appendChild(body);bench.appendChild(table);
}else{bench.textContent='尚未生成对比报告';bench.className='muted'}
document.getElementById('export').addEventListener('click',()=>{
  const reviews=[...document.querySelectorAll('textarea')].map(area=>({candidate_id:area.dataset.candidateId,feedback:area.value,timestamp:new Date().toISOString()}));
  const blob=new Blob([JSON.stringify({status:'complete',reviews},null,2)+'\\n'],{type:'application/json'});
  const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='feedback.json';link.click();URL.revokeObjectURL(link.href);
  document.getElementById('status').textContent=storageAvailable?'已导出；本机草稿仍会保留':'已导出';
});
</script>
</body>
</html>
"""


def _metric(value: object, percent: bool = False) -> str:
    if not isinstance(value, dict) or value.get("mean") is None:
        return "n/a"
    mean = float(value["mean"])
    stddev = float(value.get("stddev") or 0)
    if percent:
        return f"{mean * 100:.1f}% ± {stddev * 100:.1f}%"
    return f"{mean:.2f} ± {stddev:.2f}"


def _candidate_map(configurations: list[str], iteration: object, reveal: bool) -> dict[str, str]:
    if reveal:
        return {name: name for name in configurations}
    ordered = sorted(
        configurations,
        key=lambda name: hashlib.sha256(f"{iteration}:{name}".encode()).hexdigest(),
    )
    return {name: f"候选 {chr(65 + index)}" for index, name in enumerate(ordered)}


def _output_files(outputs: Path) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    if not outputs.is_dir():
        return files
    for path in sorted(outputs.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink() or not path.is_file():
            continue
        preview: str | None = None
        data_url: str | None = None
        if path.suffix.lower() in TEXT_SUFFIXES:
            try:
                text = path.read_text(encoding="utf-8")
                preview = text[:MAX_PREVIEW_CHARS]
                if len(text) > MAX_PREVIEW_CHARS:
                    preview += "\n…预览已截断…"
            except UnicodeDecodeError:
                preview = None
        mime_type = IMAGE_MIME_TYPES.get(path.suffix.lower())
        if mime_type and path.stat().st_size <= MAX_EMBED_BYTES:
            data_url = (
                f"data:{mime_type};base64,"
                + base64.b64encode(path.read_bytes()).decode("ascii")
            )
        files.append(
            {
                "name": path.relative_to(outputs).as_posix(),
                "size": path.stat().st_size,
                "preview": preview,
                "data_url": data_url,
            }
        )
    return files


def build_review_data(root: Path, reveal: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = load_json(root / "run_plan.json")
    if not isinstance(plan, dict) or not isinstance(plan.get("runs"), list):
        raise ValueError("run_plan.json 缺少 runs 数组")
    configurations = plan.get("configurations")
    if not isinstance(configurations, list) or not all(
        isinstance(value, str) for value in configurations
    ):
        raise ValueError("run_plan.json 缺少 configurations")
    labels = _candidate_map(configurations, plan.get("iteration"), reveal)
    grouped: dict[str, dict[str, Any]] = {}
    manifest_runs: dict[str, str] = {}
    for run in plan["runs"]:
        if not isinstance(run, dict):
            raise ValueError("run_plan.runs 项必须是对象")
        run_dir = Path(str(run.get("run_dir", ""))).expanduser().resolve()
        try:
            run_dir.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"run_dir 越出 iteration：{run_dir}") from exc
        run_id = str(run.get("run_id"))
        candidate_id = "review-" + hashlib.sha256(run_id.encode()).hexdigest()[:12]
        manifest_runs[candidate_id] = run_id
        grading_path = run_dir / "grading.json"
        grading: list[dict[str, Any]] = []
        if grading_path.is_file():
            grading_data = load_json(grading_path)
            if isinstance(grading_data, dict) and isinstance(
                grading_data.get("expectations"), list
            ):
                grading = grading_data["expectations"]
        eval_name = str(run.get("eval_name"))
        item = grouped.setdefault(
            eval_name,
            {"name": eval_name, "prompt": str(run.get("prompt", "")), "runs": []},
        )
        item["runs"].append(
            {
                "candidate_id": candidate_id,
                "candidate": labels[str(run.get("configuration"))],
                "repetition": run.get("repetition"),
                "files": _output_files(run_dir / "outputs"),
                "grading": grading,
            }
        )

    benchmark_rows: list[dict[str, object]] = []
    benchmark_path = root / "benchmark.json"
    if benchmark_path.is_file():
        benchmark = load_json(benchmark_path)
        summaries = benchmark.get("configurations", {}) if isinstance(benchmark, dict) else {}
        if isinstance(summaries, dict):
            for configuration in configurations:
                summary = summaries.get(configuration, {})
                if not isinstance(summary, dict):
                    continue
                benchmark_rows.append(
                    {
                        "candidate": labels[configuration],
                        "runs": summary.get("runs", 0),
                        "pass_rate": _metric(summary.get("pass_rate"), percent=True),
                        "duration": _metric(summary.get("duration_seconds")),
                        "tokens": _metric(summary.get("total_tokens")),
                    }
                )

    title = f"{plan.get('skill_name', 'Skill')} · iteration-{plan.get('iteration')}"
    if plan.get("schema_version") == 2:
        title += f" · {plan.get('model')}"
    data = {
        "title": title,
        "evals": list(grouped.values()),
        "benchmark": benchmark_rows,
    }
    manifest = {
        "schema_version": 1,
        "blind": not reveal,
        "model": plan.get("model"),
        "executor": plan.get("executor"),
        "candidates": labels,
        "runs": manifest_runs,
    }
    return data, manifest


def generate_review(
    iteration_path: str | Path,
    output: str | Path | None = None,
    reveal: bool = False,
    replace: bool = False,
) -> tuple[Path, Path]:
    root = Path(iteration_path).expanduser().resolve()
    output_path = (
        Path(output).expanduser().resolve() if output is not None else root / "review.html"
    )
    manifest_path = root / "review_manifest.json"
    if not replace and (output_path.exists() or manifest_path.exists()):
        raise FileExistsError("评审输出已存在；使用 --replace 明确覆盖")
    data, manifest = build_review_data(root, reveal=reveal)
    encoded = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(
        ">", "\\u003e"
    )
    title = str(data["title"]).replace("&", "&amp;").replace("<", "&lt;").replace(
        ">", "&gt;"
    )
    html = HTML_TEMPLATE.replace("__TITLE__", title).replace("__DATA__", encoded)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8", newline="\n")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return output_path, manifest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成默认隐藏版本身份的本地 Skill 评审页")
    parser.add_argument("iteration_path", help="iteration-N 目录")
    parser.add_argument("--output", help="HTML 输出路径，默认 iteration/review.html")
    parser.add_argument("--reveal", action="store_true", help="在页面中显示真实配置名")
    parser.add_argument("--replace", action="store_true", help="明确覆盖已有评审输出")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output, manifest = generate_review(
            args.iteration_path,
            output=args.output,
            reveal=args.reveal,
            replace=args.replace,
        )
    except (ValueError, FileExistsError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"已创建评审页：{output}")
    print(f"候选映射：{manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
