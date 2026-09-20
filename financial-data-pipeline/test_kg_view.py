import sys
from pathlib import Path

kg_path = Path("c:/hackathon/QUANTEXA/openclaw/skills/knowledge-graph/scripts")
sys.path.insert(0, str(kg_path))

from dynamic_execution_engine import DynamicExecutionEngine

eng = DynamicExecutionEngine()

q1 = """
MATCH (p:ExecutionPipeline {name: 'QuantitativeMultiAssetPipeline'})-[:CONTAINS_LAYER]->(l:PipelineLayer)
RETURN l.layer_number AS layer, l.name AS name, l.script AS script
ORDER BY layer
"""
print("=== 7-LAYER PIPELINE IN NEO4J ===")
for r in eng.run_query(q1):
    print(f"  Layer {r['layer']}: {r['name']} ({r['script']})")

q2 = """
MATCH (b:AnalysisBatch {batch_id: 'TEST_BATCH_01'})-[r]->(target)
RETURN type(r) AS rel, labels(target)[0] AS target_type, count(*) AS count
GROUP BY type(r), labels(target)[0]
"""
print("\n=== TEST_BATCH_01 NODES IN NEO4J ===")
for r in eng.run_query(q2):
    print(f"  -[:{r['rel']}]-> (:{r['target_type']}) (count: {r['count']})")

q3 = """
MATCH (qr:QUBOResult {batch_id: 'TEST_BATCH_01'})-[:SOLVED_BY]->(s:QUBOSolver)
RETURN s.name AS solver, qr.expected_return AS ret, qr.volatility AS vol, qr.sharpe_ratio AS sharpe, qr.btc_weight AS btc, qr.gold_weight AS gold, qr.nvda_weight AS nvda
"""
print("\n=== LAYER 7 QUBO RESULTS IN NEO4J ===")
for r in eng.run_query(q3):
    print(f"  {r['solver']:<22} | Return: {r['ret']*100:.2f}% | Vol: {r['vol']*100:.2f}% | BTC: {r['btc']*100:.0f}% | GOLD: {r['gold']*100:.0f}% | NVDA: {r['nvda']*100:.0f}%")

eng.close()
