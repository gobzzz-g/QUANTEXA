import { BookOpen, CheckCircle } from 'lucide-react';

export function Methodology() {
  return (
    <div className="space-y-8 flex flex-col h-full max-w-4xl mx-auto py-8">
      <div className="flex gap-4 items-center border-b border-border pb-6">
        <BookOpen className="text-primary w-8 h-8" />
        <h2 className="text-3xl font-bold">QuantExa Engine Methodology</h2>
      </div>

      <div className="space-y-6 text-text-muted leading-relaxed">
        <p className="text-lg text-text">
          The QuantExa platform is built on strict institutional-grade assumptions to prevent common retail backtesting fallacies like look-ahead bias and unrealistic execution pricing.
        </p>

        <section className="bg-surface rounded-lg p-6 border border-border">
          <h3 className="text-xl font-bold text-text mb-4">Signal Generation & Execution</h3>
          <ul className="space-y-4">
            <li className="flex gap-3">
              <CheckCircle className="text-accent shrink-0 mt-0.5" size={18} />
              <div>
                <strong className="text-text block">Signal at Close (t)</strong>
                All technical indicators (SMA, EMA, Z-Scores) and resulting trade signals are evaluated strictly at the Close of the current bar t.
              </div>
            </li>
            <li className="flex gap-3">
              <CheckCircle className="text-accent shrink-0 mt-0.5" size={18} />
              <div>
                <strong className="text-text block">Execution at Next Open (t+1)</strong>
                To prevent look-ahead bias, it is impossible to execute a trade at the close price of the bar that just generated the signal. Executions occur at the exact Open price of the *subsequent* bar (t+1).
              </div>
            </li>
            <li className="flex gap-3">
              <CheckCircle className="text-accent shrink-0 mt-0.5" size={18} />
              <div>
                <strong className="text-text block">Indicator Warm-up</strong>
                If a strategy requires a 200-day lookback, no trades can be generated until the 201st day. Missing values are filled neutrally and strictly prevent early execution.
              </div>
            </li>
          </ul>
        </section>

        <section className="bg-surface rounded-lg p-6 border border-border">
          <h3 className="text-xl font-bold text-text mb-4">Accounting Identity</h3>
          <p className="mb-4">
            The fundamental accounting equation is strictly maintained at every time step t:
          </p>
          <div className="bg-surface-highlight p-4 rounded font-mono text-center text-primary mb-4 text-lg">
            Equity[t] = Cash[t] + (Units[t] × Price[t])
          </div>
          <p>
            When a trade is executed, Cash is deducted by exactly (Units × Execution Price) + Fees. The engine supports fractional position sizing (default 1.0 = 100% of equity).
          </p>
        </section>

        <section className="bg-surface rounded-lg p-6 border border-border">
          <h3 className="text-xl font-bold text-text mb-4">Transaction Costs</h3>
          <ul className="space-y-3">
            <li><strong className="text-text">Commissions:</strong> Expressed as a percentage of the gross trade value. Deducted directly from cash during execution.</li>
            <li><strong className="text-text">Slippage:</strong> Expressed in basis points (bps). Assuming 1 bps = 0.01%. The execution price is worsened by the slippage amount. For a long entry, execution price becomes Open × (1 + slippage).</li>
          </ul>
        </section>

        <section className="bg-surface rounded-lg p-6 border border-border">
          <h3 className="text-xl font-bold text-text mb-4">Benchmark Comparison</h3>
          <p>
            The Buy & Hold benchmark uses the identical mathematical constraints as the active strategy:
          </p>
          <ul className="list-disc list-inside mt-2 space-y-1 pl-2">
            <li>It begins on the same exact first actionable date (accounting for warm-up).</li>
            <li>It enters at the exact same Open price as the strategy's theoretical first trade.</li>
            <li>It is subjected to the same commission and slippage costs upon initial entry.</li>
            <li>Its metrics (CAGR, Sharpe, Max Drawdown) are calculated using the identical formulas.</li>
          </ul>
        </section>
      </div>
    </div>
  );
}
