#!/usr/bin/env python3
"""Read only git blobs; reproduce Epic 3 architecture and size observations."""
import argparse
import ast
import collections
import hashlib
import json
import subprocess
from pathlib import Path

BASE = '6644902c9e3880482d1edef75c42a1ee303ba6dd'
HEAD = '82b4b567f27c788e062a7bc8310d0c660c69d666'
ROOT = Path(__file__).resolve().parents[3]

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True)

def module(path):
    return path.removesuffix('.py').replace('/', '.').removesuffix('.__init__')

def cycles(graph):
    index = 0
    seen, low, stack, active, result = {}, {}, [], set(), []
    def visit(v):
        nonlocal index
        seen[v] = low[v] = index
        index += 1
        stack.append(v)
        active.add(v)
        for w in sorted(graph[v]):
            if w not in seen:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in active:
                low[v] = min(low[v], seen[w])
        if low[v] == seen[v]:
            group = []
            while True:
                w = stack.pop()
                active.remove(w)
                group.append(w)
                if w == v:
                    break
            if len(group) > 1 or v in graph[v]:
                result.append(sorted(group))
    for v in sorted(graph):
        if v not in seen:
            visit(v)
    return sorted(result)

def snapshot(ref):
    paths = git('ls-tree', '-r', '--name-only', ref).splitlines()
    code = [p for p in paths if p.startswith(('booking_app/', 'scripts/', 'tests/')) and Path(p).suffix in ('.py', '.js', '.cjs', '.html', '.css', '.sql')]
    sources = {p: git('show', f'{ref}:{p}') for p in code}
    sizes = [{'path': p, 'lines': len(s.splitlines()), 'bytes': len(s.encode()), 'sha256': hashlib.sha256(s.encode()).hexdigest()} for p,s in sources.items()]
    product_python = {p: ast.parse(s, p) for p,s in sources.items() if p.startswith('booking_app/') and p.endswith('.py')}
    modules = {module(p): p for p in product_python}
    graph = {m: set() for m in modules}
    edges, external, sql, functions, classes, duplicates = [], [], [], [], [], collections.defaultdict(list)
    for path, tree in product_python.items():
        m = module(path)
        package = m if path.endswith('__init__.py') else m.rsplit('.', 1)[0]
        def add_import(target, line):
            # Importing a symbol resolves to the longest existing module prefix.
            current = target
            while current and current not in modules:
                current = current.rsplit('.', 1)[0] if '.' in current else ''
            if current:
                if current != m:
                    graph[m].add(current)
                    edges.append({'from': m, 'to': current, 'path': path, 'line': line})
            else:
                external.append({'from': m, 'to': target, 'path': path, 'line': line})
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    add_import(alias.name, node.lineno)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ''
                if node.level:
                    parts = package.split('.')
                    base = '.'.join(parts[:len(parts)-node.level+1] + ([base] if base else []))
                for alias in node.names:
                    add_import(base + '.' + alias.name, node.lineno)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                item = {'path': path, 'name': node.name, 'line': node.lineno, 'end_line': node.end_lineno, 'span_lines': node.end_lineno-node.lineno+1, 'ast_statements': sum(isinstance(n, ast.stmt) for n in ast.walk(node))-1}
                functions.append(item)
                body = node.body[1:] if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str) else node.body
                if sum(isinstance(n, ast.stmt) for b in body for n in ast.walk(b)) >= 4:
                    duplicates[ast.dump(ast.Module(body=body, type_ignores=[]), include_attributes=False)].append(item)
            elif isinstance(node, ast.ClassDef):
                classes.append({'path': path, 'name': node.name, 'line': node.lineno, 'end_line': node.end_lineno, 'span_lines': node.end_lineno-node.lineno+1})
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ('execute', 'executemany', 'executescript', 'commit', 'rollback'):
                sql.append({'path': path, 'line': node.lineno, 'operation': node.func.attr, 'call': ast.unparse(node)[:400]})
    unique_edges = sorted({(e['from'], e['to']) for e in edges})
    return {'ref': ref, 'sizes': sorted(sizes,key=lambda x:(-x['lines'],x['path'])), 'product_python_module_count':len(modules), 'internal_edges': [list(e) for e in unique_edges], 'internal_import_sites':edges, 'external_import_sites':external, 'cycles':cycles(graph), 'sql_call_sites':sorted(sql,key=lambda x:(x['path'],x['line'])), 'sql_calls_by_file':dict(sorted(collections.Counter(x['path'] for x in sql).items())), 'functions':sorted(functions,key=lambda x:(-x['span_lines'],x['path'],x['line'])), 'classes':classes, 'exact_function_body_duplicates': [v for v in duplicates.values() if len(v)>1]}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base',default=BASE)
    ap.add_argument('--head',default=HEAD)
    ap.add_argument('--output',type=Path,default=Path(__file__).with_name('epic-3-aggregate.json'))
    args=ap.parse_args()
    before,after=snapshot(args.base),snapshot(args.head)
    a={x['path']:x for x in before['sizes']}; b={x['path']:x for x in after['sizes']}
    growth=[{'path':p,'before_lines':a.get(p,{}).get('lines',0),'after_lines':b.get(p,{}).get('lines',0),'net_lines':b.get(p,{}).get('lines',0)-a.get(p,{}).get('lines',0)} for p in sorted(a.keys()|b.keys())]
    ea={tuple(e) for e in before['internal_edges']}; eb={tuple(e) for e in after['internal_edges']}
    fa={(f['path'],f['name']):f for f in before['functions']}; fb={(f['path'],f['name']):f for f in after['functions']}
    func_growth=[{'path':k[0],'name':k[1],'before_span':fa.get(k,{}).get('span_lines',0),'after_span':fb.get(k,{}).get('span_lines',0),'before_statements':fa.get(k,{}).get('ast_statements',0),'after_statements':fb.get(k,{}).get('ast_statements',0),'after_line':fb.get(k,{}).get('line')} for k in sorted(fa.keys()|fb.keys())]
    log=git('log','--reverse','--format=%H%x09%P%x09%s',f'{args.base}..{args.head}').splitlines()
    commits=[{'commit':c.split('\t',2)[0],'parents':c.split('\t',2)[1].split(),'subject':c.split('\t',2)[2]} for c in log]
    path_sources={p:git('log','--format=%H %s',f'{args.base}..{args.head}','--',p).splitlines() for p in b if p.startswith('booking_app/')}
    report={'schema_version':1,'range':f'{args.base}..{args.head}','method':{'sources':'committed git blobs only; worktree product content ignored','dependency_scope':'all booking_app Python files; AST import graph with static relative-import resolution; external libraries excluded from SCC','sql_scope':'AST attribute calls named execute/executemany/executescript/commit/rollback in booking_app; lexical call-site evidence, not dynamic execution','size_scope':'tracked booking_app/scripts/tests .py/.js/.cjs/.html/.css/.sql; physical lines and UTF-8 bytes; evidence and framework excluded','function_scope':'all Python function/method AST spans in booking_app (nested included); physical span and AST statement counts','duplication_scope':'exact Python function bodies >=4 AST statements after removing docstring, ignores location; semantic/JS duplication requires manual review','limitations':['Import edges are static; dynamic imports/runtime injection and JS dependency graphs are not inferred.','SQL call counts are lexical, not SQL-statement counts or a proof of runtime behavior.','Line spans can hide compressed multi-statement JavaScript; inspect byte size and responsibilities.','Range includes interleaved Story 2.5, experiment/recording work and historical runner corrections; no exclusive Epic 3 attribution.','No runtime tests are executed by this derivation; acceptance and process causality are out of scope.']},'commits':commits,'before':before,'after':after,'edge_delta':{'added':[list(e) for e in sorted(eb-ea)],'removed':[list(e) for e in sorted(ea-eb)]},'file_growth':sorted(growth,key=lambda x:(-x['net_lines'],x['path'])),'function_growth':func_growth,'product_path_commit_sources':path_sources}
    evidence=ROOT/'docs/evidence/retrospectives/epic-3-git.json'
    if evidence.exists():
        e=json.loads(evidence.read_text())
        report['churn_prepass']={'path':str(evidence.relative_to(ROOT)),'range':e['range'],'commit_count':e['commit_count'],'merge_count':e['merge_count'],'merges_measured':e['merges_measured'],'product_files':[f for f in e['files'] if f['path'].startswith('booking_app/')],'merge_files':e['merge_files'],'interpretation':'files is non-merge summed churn, not absolute size; merge_files is kept separate; binary revisions are unmeasured churn'}
    report['accepted_head_report_fingerprints'] = []
    for report_path in ['docs/evidence/story-3.4-review-fixes/parent-http/result.json', 'docs/evidence/story-3.4-review-fixes/browser/result.json']:
        saved = json.loads(git('show', f'{args.head}:{report_path}'))
        hashes = saved['source_sha256']
        mismatches = [p for p,h in hashes.items() if hashlib.sha256(subprocess.check_output(['git','-C',str(ROOT),'show',f'{args.head}:{p}'])).hexdigest() != h]
        report['accepted_head_report_fingerprints'].append({'path':report_path,'run_id':saved['run_id'],'recorded_result':saved['result'],'file_count':len(hashes),'before_after_equal':hashes == saved['source_sha256_after'],'head_mismatch_paths':mismatches,'meaning':'Saved report source bindings checked against accepted commit; report result is historical, not a new runtime execution.'})
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'output':str(args.output),'modules':[before['product_python_module_count'],after['product_python_module_count']],'edges':[len(before['internal_edges']),len(after['internal_edges'])],'cycles':[before['cycles'],after['cycles']],'edge_delta':report['edge_delta'],'sql_counts':[before['sql_calls_by_file'],after['sql_calls_by_file']],'largest_app_files':[x for x in after['sizes'] if x['path'].startswith('booking_app/')][:6],'largest_functions':after['functions'][:5]},ensure_ascii=False,indent=2))
if __name__=='__main__':
    main()
