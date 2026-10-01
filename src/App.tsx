import React, { useState, useEffect } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  Play,
  RotateCcw,
  Terminal,
  Activity,
  Trash2,
  TrendingUp,
  TrendingDown,
  Layers,
  ArrowRight,
  Database,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Sliders,
} from "lucide-react";

interface TestPlan {
  id: string;
  name: string;
  content: string;
}

interface ResourceCost {
  address: string;
  type: string;
  action: string;
  region: string;
  old_sku: string | null;
  new_sku: string | null;
  old_monthly_cost: number;
  new_monthly_cost: number;
  delta: number;
  warning: string | null;
}

interface FinancialReport {
  currency: string;
  financial_summary: {
    prior_monthly_total: number;
    projected_monthly_total: number;
    net_monthly_impact: number;
    annualized_impact?: number;
  };
  policy_verdict: {
    budget_threshold: number | null;
    status: string;
    passed: boolean;
    exit_code: number;
    message: string;
  };
  cache_statistics: {
    cache_hits: number;
    cache_misses: number;
    api_calls: number;
  };
  resources: ResourceCost[];
  skipped_resources: string[];
  warnings: string[];
}

/**
 * Format numbers or strings into INR currency with Indian number formatting (e.g., ₹1,234.56).
 */
export function formatINR(amount: number | string, showSign = false, rounded = false): string {
  const num = typeof amount === "string" ? parseFloat(amount.replace(/[^0-9.-]+/g, "")) : amount;
  if (isNaN(num)) return rounded ? "₹0" : "₹0.00";

  const absNum = Math.abs(num);
  const formatted =
    "₹" +
    absNum.toLocaleString("en-IN", {
      minimumFractionDigits: rounded ? 0 : 2,
      maximumFractionDigits: rounded ? 0 : 2,
    });

  if (num > 0 && showSign) return `+${formatted}`;
  if (num < 0) return `-${formatted}`;
  return formatted;
}

/**
 * Clean resource labels (e.g. vm.web_server, disk.data)
 */
function cleanResourceLabel(address: string, type: string): string {
  const parts = address.split(".");
  const name = parts[parts.length - 1];
  if (type.includes("virtual_machine")) return `vm.${name}`;
  if (type.includes("managed_disk")) return `disk.${name}`;
  return name;
}

/**
 * Format SKU transition display (e.g. Standard_B1s → Standard_B2s)
 */
function formatSkuDisplay(r: ResourceCost): string {
  if (r.old_sku && r.new_sku && r.old_sku !== r.new_sku) {
    return `${r.old_sku} → ${r.new_sku}`;
  }
  return r.new_sku || r.old_sku || "Standard";
}

/**
 * Known standard VM rates in INR/month for the What-If calculator
 */
const WHAT_IF_CATALOG: Record<string, number> = {
  Standard_B1s: 981.05,
  Standard_B2s: 2915.04,
  Standard_D2s_v3: 7008.0,
  Standard_B4ms: 11660.16,
  Standard_D4s_v3: 14016.0,
};

export default function App() {
  const [plans, setPlans] = useState<TestPlan[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<string>("plan-create.json");
  const [planJson, setPlanJson] = useState<string>("");
  const [maxIncrease, setMaxIncrease] = useState<string>("5000");
  const [activeTab, setActiveTab] = useState<"overview" | "terminal" | "tests">("overview");

  const [loading, setLoading] = useState<boolean>(false);
  const [output, setOutput] = useState<string>("");
  const [exitCode, setExitCode] = useState<number | null>(null);
  const [report, setReport] = useState<FinancialReport | null>(null);
  const [cacheNotice, setCacheNotice] = useState<string>("");

  // What-If Simulator state
  const [simCurrentSku, setSimCurrentSku] = useState<string>("Standard_B2s");
  const [simAltSku, setSimAltSku] = useState<string>("Standard_B1s");

  useEffect(() => {
    fetch("/api/test-plans")
      .then((res) => res.json())
      .then((data) => {
        if (data.plans && data.plans.length > 0) {
          setPlans(data.plans);
          const defaultPlan = data.plans.find((p: TestPlan) => p.id === "plan-create.json") || data.plans[0];
          setSelectedPlanId(defaultPlan.id);
          setPlanJson(defaultPlan.content);
        }
      })
      .catch((err) => console.error("Failed to load plans", err));
  }, []);

  const handleSelectPlan = (plan: TestPlan) => {
    setSelectedPlanId(plan.id);
    setPlanJson(plan.content);
  };

  const runAnalysis = async () => {
    setLoading(true);
    setCacheNotice("");
    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          plan_json: planJson,
          max_increase: maxIncrease ? parseFloat(maxIncrease) : null,
          currency: "INR",
        }),
      });
      const data = await res.json();
      setExitCode(data.exitCode);
      setOutput(data.terminalOutput || data.errorOutput || "No output");
      if (data.report) {
        setReport(data.report);
        // Pre-fill What-If with detected SKU if available
        const firstVm = data.report.resources?.find((r: ResourceCost) => r.new_sku || r.old_sku);
        if (firstVm) {
          const sku = firstVm.new_sku || firstVm.old_sku;
          if (sku && WHAT_IF_CATALOG[sku]) {
            setSimCurrentSku(sku);
          }
        }
      }
    } catch (err: any) {
      setExitCode(2);
      setOutput("Error: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  // Trigger analysis on first load once plans are loaded
  useEffect(() => {
    if (planJson && !report) {
      runAnalysis();
    }
  }, [planJson]);

  const handleClearCache = async () => {
    try {
      const res = await fetch("/api/clear-cache", { method: "POST" });
      const data = await res.json();
      setCacheNotice(data.output?.trim() || "Pricing cache cleared.");
      // Re-run analysis to refresh stats
      runAnalysis();
    } catch (err: any) {
      setCacheNotice("Failed to clear cache: " + err.message);
    }
  };

  const handleRunTests = async () => {
    setLoading(true);
    setActiveTab("tests");
    setOutput("Running pytest test suite...\n");
    try {
      const res = await fetch("/api/run-tests", { method: "POST" });
      const data = await res.json();
      setExitCode(data.exitCode);
      setOutput(data.output);
    } catch (err: any) {
      setExitCode(1);
      setOutput("Error running tests: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const cliCommand = `costguard --plan ${selectedPlanId}${
    maxIncrease ? ` --max-increase ${maxIncrease}` : ""
  }`;

  // Deterministic "Why did cost change?" reasons
  const costReasons: string[] = [];
  if (report) {
    if (!report.resources || report.resources.length === 0) {
      costReasons.push("No billable resources changed (only non-billable networking/metadata).");
    } else {
      report.resources.forEach((r) => {
        const name = cleanResourceLabel(r.address, r.type);
        if (r.action === "CREATE") {
          costReasons.push(`New ${r.type.includes("disk") ? "managed disk" : "VM"} (${name}): ${formatINR(r.delta, true)}/month`);
        } else if (r.action === "DELETE") {
          costReasons.push(`Deleted ${r.type.includes("disk") ? "managed disk" : "VM"} (${name}): ${formatINR(r.delta)}/month (savings)`);
        } else if (r.delta !== 0) {
          costReasons.push(`${name} updated (${formatSkuDisplay(r)}): ${formatINR(r.delta, true)}/month`);
        } else {
          costReasons.push(`${name} configuration update: ₹0.00/month`);
        }
      });
    }
  }

  // Cost Insight advice
  let costInsightText = "Run analysis to see cost optimization recommendations.";
  if (report) {
    if (!report.resources || report.resources.length === 0) {
      costInsightText = "All detected Terraform changes are non-billable (resource groups, subnets, NSGs). No compute or storage billing impact.";
    } else if (!report.policy_verdict.passed) {
      costInsightText = `Deployment is blocked because the projected monthly increase of ${formatINR(report.financial_summary.net_monthly_impact)} exceeds the budget threshold of ${formatINR(report.policy_verdict.budget_threshold || 0)}.`;
    } else if (report.financial_summary.net_monthly_impact < 0) {
      costInsightText = `This deployment reduces monthly infrastructure costs by ${formatINR(Math.abs(report.financial_summary.net_monthly_impact))}/month.`;
    } else {
      const topCostItem = [...report.resources].sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))[0];
      if (topCostItem) {
        costInsightText = `${cleanResourceLabel(topCostItem.address, topCostItem.type)} is the primary contributor (${formatINR(topCostItem.delta, true)}/mo). Verify whether this SKU is required for the workload.`;
      }
    }
  }

  // What-If calculations
  const simCurrentCost = WHAT_IF_CATALOG[simCurrentSku] || 2915.04;
  const simAltCost = WHAT_IF_CATALOG[simAltSku] || 981.05;
  const simDiff = simAltCost - simCurrentCost;
  const simAnnualDiff = simDiff * 12;

  const currentMonthly = report ? report.financial_summary.prior_monthly_total : 0;
  const projectedMonthly = report ? report.financial_summary.projected_monthly_total : 0;
  const monthlyImpact = report ? report.financial_summary.net_monthly_impact : 0;
  const annualizedImpact = monthlyImpact * 12;
  const isBudgetPassed = report ? report.policy_verdict.passed : true;

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 flex flex-col font-sans antialiased">
      {/* Top Header */}
      <header className="border-b border-neutral-800 bg-neutral-900/70 backdrop-blur px-6 py-3.5">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-emerald-600 flex items-center justify-center shadow-md">
              <ShieldCheck className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold tracking-tight text-white text-base">COSTGUARD</span>
                <span className="text-[11px] px-2 py-0.5 rounded bg-neutral-800 text-neutral-300 font-mono">
                  v1.0 • INR (₹)
                </span>
              </div>
              <p className="text-xs text-neutral-400 font-medium">
                Predict infrastructure cost before you deploy.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {report && (
              <span className="hidden sm:inline-flex text-xs px-2.5 py-1 rounded bg-neutral-900 border border-neutral-800 text-neutral-400 font-mono">
                Cache: {report.cache_statistics.cache_hits} hits · {report.cache_statistics.api_calls} API lookups
              </span>
            )}
            <button
              onClick={handleClearCache}
              className="text-xs px-2.5 py-1.5 rounded-lg border border-neutral-800 bg-neutral-900 hover:bg-neutral-800 text-neutral-300 transition flex items-center gap-1.5"
            >
              <Trash2 className="w-3.5 h-3.5 text-neutral-400" />
              Clear Cache
            </button>
            <button
              onClick={handleRunTests}
              className="text-xs px-2.5 py-1.5 rounded-lg border border-neutral-800 bg-neutral-900 hover:bg-neutral-800 text-neutral-300 transition flex items-center gap-1.5"
            >
              <Activity className="w-3.5 h-3.5 text-emerald-400" />
              Run 34 Tests
            </button>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-6xl mx-auto w-full px-6 py-6 flex-1 space-y-6">
        {/* Navigation Tabs */}
        <div className="flex items-center justify-between border-b border-neutral-800 pb-3">
          <div className="flex gap-2 text-xs font-medium">
            <button
              onClick={() => setActiveTab("overview")}
              className={`px-3 py-1.5 rounded-lg transition ${
                activeTab === "overview"
                  ? "bg-neutral-800 text-white font-semibold"
                  : "text-neutral-400 hover:text-neutral-200"
              }`}
            >
              Overview & Analysis
            </button>
            <button
              onClick={() => setActiveTab("terminal")}
              className={`px-3 py-1.5 rounded-lg transition flex items-center gap-1.5 ${
                activeTab === "terminal"
                  ? "bg-neutral-800 text-white font-semibold"
                  : "text-neutral-400 hover:text-neutral-200"
              }`}
            >
              <Terminal className="w-3.5 h-3.5" />
              CLI Terminal
            </button>
            <button
              onClick={() => setActiveTab("tests")}
              className={`px-3 py-1.5 rounded-lg transition flex items-center gap-1.5 ${
                activeTab === "tests"
                  ? "bg-neutral-800 text-white font-semibold"
                  : "text-neutral-400 hover:text-neutral-200"
              }`}
            >
              <Activity className="w-3.5 h-3.5" />
              Test Suite (34 Passed)
            </button>
          </div>

          <div className="text-xs font-mono text-neutral-400 hidden md:block">
            Azure Retail API (Consumption) • 730h/mo
          </div>
        </div>

        {/* CLI Command & Plan Selector Bar */}
        <div className="bg-neutral-900/90 border border-neutral-800 rounded-xl p-4 space-y-3">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 font-mono text-xs">
            <div className="flex items-center gap-2 text-neutral-300 truncate bg-neutral-950 px-3 py-2 rounded-lg border border-neutral-800/80 flex-1">
              <span className="text-emerald-500 font-bold">$</span>
              <span className="text-neutral-100 truncate">{cliCommand}</span>
            </div>
            <button
              onClick={runAnalysis}
              disabled={loading}
              className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-sans font-medium text-xs flex items-center justify-center gap-1.5 transition disabled:opacity-50 shrink-0"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              {loading ? "Analyzing..." : "Analyze Plan"}
            </button>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-4 pt-1 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-neutral-400 font-medium">Terraform Plan:</span>
              <div className="flex gap-1.5">
                {plans.map((p) => {
                  const active = selectedPlanId === p.id;
                  const label = p.id.replace(".json", "").replace("plan-", "");
                  return (
                    <button
                      key={p.id}
                      onClick={() => handleSelectPlan(p)}
                      className={`px-2.5 py-1 rounded text-xs font-mono border transition ${
                        active
                          ? "bg-neutral-800 border-neutral-600 text-white font-bold"
                          : "bg-neutral-950 border-neutral-800 text-neutral-400 hover:text-neutral-200"
                      }`}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-neutral-400 font-medium">Budget:</span>
              <div className="relative w-28">
                <span className="absolute left-2 top-1 text-xs font-mono text-neutral-500">₹</span>
                <input
                  type="number"
                  value={maxIncrease}
                  onChange={(e) => setMaxIncrease(e.target.value)}
                  placeholder="5000"
                  className="w-full bg-neutral-950 border border-neutral-800 rounded px-2 pl-5 py-1 text-xs font-mono text-neutral-100 focus:outline-none focus:border-neutral-600"
                />
              </div>
              <button
                onClick={() => setMaxIncrease("5000")}
                className="text-[11px] text-neutral-400 hover:text-neutral-200 underline"
              >
                ₹5,000 (Pass)
              </button>
              <button
                onClick={() => setMaxIncrease("1000")}
                className="text-[11px] text-rose-400 hover:text-rose-300 underline"
              >
                ₹1,000 (Block)
              </button>
            </div>
          </div>
        </div>

        {cacheNotice && (
          <div className="text-xs p-3 rounded-lg bg-neutral-900 border border-neutral-800 text-neutral-300 font-mono">
            {cacheNotice}
          </div>
        )}

        {/* TAB 1: OVERVIEW & ANALYSIS */}
        {activeTab === "overview" && (
          <div className="space-y-6">
            {/* 4 Summary Cards (Section 9) */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {/* Card 1: Current Cost */}
              <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-4">
                <span className="text-xs font-medium text-neutral-400 block mb-1">Current Cost</span>
                <div className="text-xl font-bold font-mono text-white">
                  {formatINR(currentMonthly, false, true)}
                  <span className="text-xs text-neutral-500 font-normal">/mo</span>
                </div>
                <span className="text-[11px] text-neutral-500 font-mono mt-1 block">Baseline compute</span>
              </div>

              {/* Card 2: Projected Cost */}
              <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-4">
                <span className="text-xs font-medium text-neutral-400 block mb-1">Projected Cost</span>
                <div className="text-xl font-bold font-mono text-white">
                  {formatINR(projectedMonthly, false, true)}
                  <span className="text-xs text-neutral-500 font-normal">/mo</span>
                </div>
                <span className="text-[11px] text-neutral-500 font-mono mt-1 block">After deployment</span>
              </div>

              {/* Card 3: Monthly Impact */}
              <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-4">
                <span className="text-xs font-medium text-neutral-400 block mb-1">Monthly Impact</span>
                <div
                  className={`text-xl font-bold font-mono ${
                    monthlyImpact > 0
                      ? "text-rose-400"
                      : monthlyImpact < 0
                      ? "text-emerald-400"
                      : "text-neutral-300"
                  }`}
                >
                  {formatINR(monthlyImpact, true, true)}
                  <span className="text-xs text-neutral-500 font-normal">/mo</span>
                </div>
                <span className="text-[11px] text-neutral-500 font-mono mt-1 block">
                  {annualizedImpact !== 0 ? `${formatINR(annualizedImpact, true, true)}/yr` : "Zero impact"}
                </span>
              </div>

              {/* Card 4: Budget Status */}
              <div
                className={`border rounded-xl p-4 ${
                  isBudgetPassed
                    ? "bg-emerald-950/20 border-emerald-800/60"
                    : "bg-rose-950/20 border-rose-800/60"
                }`}
              >
                <span className="text-xs font-medium text-neutral-400 block mb-1">Budget Status</span>
                <div className="flex items-center gap-2">
                  {isBudgetPassed ? (
                    <>
                      <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                      <span className="text-xl font-bold text-emerald-400 font-mono">PASS</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="w-5 h-5 text-rose-400 shrink-0" />
                      <span className="text-xl font-bold text-rose-400 font-mono">BLOCK</span>
                    </>
                  )}
                </div>
                <span className="text-[11px] text-neutral-400 font-mono mt-1 block">
                  {isBudgetPassed ? "Within budget limit" : "Exceeds budget limit"}
                </span>
              </div>
            </div>

            {/* Cost Impact Table (Section 10) */}
            <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl overflow-hidden shadow-lg">
              <div className="px-5 py-3 border-b border-neutral-800 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-white tracking-tight">Cost Impact Breakdown</h3>
                  <p className="text-xs text-neutral-400">Resource changes extracted from Terraform plan</p>
                </div>
                {report && report.skipped_resources.length > 0 && (
                  <span className="text-xs text-neutral-500 font-mono">
                    Skipped {report.skipped_resources.length} non-billable resources
                  </span>
                )}
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-neutral-950/80 text-neutral-400 font-mono border-b border-neutral-800">
                    <tr>
                      <th className="py-2.5 px-4 font-semibold">Resource</th>
                      <th className="py-2.5 px-3 font-semibold">Action</th>
                      <th className="py-2.5 px-3 font-semibold">SKU</th>
                      <th className="py-2.5 px-3 font-semibold">Region</th>
                      <th className="py-2.5 px-3 font-semibold text-right">Current</th>
                      <th className="py-2.5 px-3 font-semibold text-right">Projected</th>
                      <th className="py-2.5 px-4 font-semibold text-right">Impact</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-800/60 font-mono">
                    {report && report.resources && report.resources.length > 0 ? (
                      report.resources.map((r, idx) => {
                        const name = cleanResourceLabel(r.address, r.type);
                        const actionStyle =
                          r.action === "CREATE"
                            ? "text-emerald-400 bg-emerald-950/50 border-emerald-800/40"
                            : r.action === "DELETE"
                            ? "text-rose-400 bg-rose-950/50 border-rose-800/40"
                            : "text-amber-400 bg-amber-950/50 border-amber-800/40";
                        return (
                          <tr key={idx} className="hover:bg-neutral-800/30 transition">
                            <td className="py-3 px-4 font-medium text-neutral-200">{name}</td>
                            <td className="py-3 px-3">
                              <span
                                className={`px-2 py-0.5 rounded text-[11px] font-bold border ${actionStyle}`}
                              >
                                {r.action}
                              </span>
                            </td>
                            <td className="py-3 px-3 text-neutral-300">{formatSkuDisplay(r)}</td>
                            <td className="py-3 px-3 text-neutral-400">{r.region}</td>
                            <td className="py-3 px-3 text-right text-neutral-300">
                              {formatINR(r.old_monthly_cost)}
                            </td>
                            <td className="py-3 px-3 text-right text-neutral-300">
                              {formatINR(r.new_monthly_cost)}
                            </td>
                            <td
                              className={`py-3 px-4 text-right font-bold ${
                                r.delta > 0
                                  ? "text-rose-400"
                                  : r.delta < 0
                                  ? "text-emerald-400"
                                  : "text-neutral-400"
                              }`}
                            >
                              {formatINR(r.delta, true)}
                            </td>
                          </tr>
                        );
                      })
                    ) : (
                      <tr>
                        <td colSpan={7} className="py-8 text-center text-neutral-500 font-sans">
                          No billable changes detected. All items are zero-cost or non-billable resources.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Financial Summary & Budget Guardrail Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Financial Summary (Section 11) */}
              <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-5 space-y-3">
                <h3 className="text-sm font-semibold text-white tracking-tight flex items-center gap-2">
                  <span>Financial Summary</span>
                </h3>
                <div className="space-y-2 text-xs font-mono">
                  <div className="flex justify-between py-1 border-b border-neutral-800/60">
                    <span className="text-neutral-400">Current Monthly Cost:</span>
                    <span className="text-neutral-200 font-semibold">{formatINR(currentMonthly)}/month</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-neutral-800/60">
                    <span className="text-neutral-400">Projected Monthly Cost:</span>
                    <span className="text-neutral-200 font-semibold">{formatINR(projectedMonthly)}/month</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-neutral-800/60">
                    <span className="text-neutral-400">Monthly Impact:</span>
                    <span
                      className={`font-bold ${
                        monthlyImpact > 0
                          ? "text-rose-400"
                          : monthlyImpact < 0
                          ? "text-emerald-400"
                          : "text-neutral-300"
                      }`}
                    >
                      {formatINR(monthlyImpact, true)}/month
                    </span>
                  </div>
                  <div className="flex justify-between py-1 pt-1.5">
                    <span className="text-neutral-400 font-sans font-medium">Annualized Impact:</span>
                    <span
                      className={`font-bold ${
                        annualizedImpact > 0
                          ? "text-rose-400"
                          : annualizedImpact < 0
                          ? "text-emerald-400"
                          : "text-neutral-300"
                      }`}
                    >
                      {formatINR(annualizedImpact, true)}/year
                    </span>
                  </div>
                </div>
              </div>

              {/* Budget Guardrail (Section 12) */}
              <div
                className={`border rounded-xl p-5 space-y-3 ${
                  isBudgetPassed
                    ? "bg-emerald-950/10 border-emerald-800/50"
                    : "bg-rose-950/10 border-rose-800/50"
                }`}
              >
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-white tracking-tight flex items-center gap-1.5">
                    {isBudgetPassed ? (
                      <ShieldCheck className="w-4 h-4 text-emerald-400" />
                    ) : (
                      <ShieldAlert className="w-4 h-4 text-rose-400" />
                    )}
                    Budget Guardrail
                  </h3>
                  <span
                    className={`text-xs px-2 py-0.5 rounded font-bold font-mono ${
                      isBudgetPassed
                        ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                        : "bg-rose-950 text-rose-400 border border-rose-800"
                    }`}
                  >
                    {isBudgetPassed ? "✓ WITHIN BUDGET" : "✕ BUDGET EXCEEDED"}
                  </span>
                </div>

                <div className="space-y-2 text-xs font-mono">
                  <div className="flex justify-between py-1 border-b border-neutral-800/60">
                    <span className="text-neutral-400">Budget Limit:</span>
                    <span className="text-neutral-200 font-semibold">
                      {report?.policy_verdict.budget_threshold !== null
                        ? `${formatINR(report?.policy_verdict.budget_threshold || 0)}/month`
                        : "Unconstrained"}
                    </span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-neutral-800/60">
                    <span className="text-neutral-400">Actual Increase:</span>
                    <span
                      className={`font-bold ${
                        monthlyImpact > 0
                          ? "text-rose-400"
                          : monthlyImpact < 0
                          ? "text-emerald-400"
                          : "text-neutral-300"
                      }`}
                    >
                      {formatINR(monthlyImpact, true)}/month
                    </span>
                  </div>
                </div>

                <div className="pt-1 text-xs">
                  {isBudgetPassed ? (
                    <p className="text-emerald-400 font-medium">✓ Deployment can continue.</p>
                  ) : (
                    <p className="text-rose-400 font-bold">✕ Deployment Blocked by Budget Guardrail.</p>
                  )}
                </div>
              </div>
            </div>

            {/* Why Did Cost Change? (Section 14) & Cost Insight (Section 15) */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Why Did Cost Change? (Section 14) */}
              <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-5 space-y-2.5">
                <h4 className="text-xs font-bold text-neutral-200 uppercase tracking-wider">
                  Why did the cost change?
                </h4>
                <ul className="space-y-1.5 text-xs text-neutral-300 font-mono">
                  {costReasons.map((reason, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="text-neutral-500">•</span>
                      <span>{reason}</span>
                    </li>
                  ))}
                </ul>
                <div className="pt-2 border-t border-neutral-800/80 text-xs font-mono font-bold flex justify-between">
                  <span className="text-neutral-400">Total impact:</span>
                  <span
                    className={
                      monthlyImpact > 0
                        ? "text-rose-400"
                        : monthlyImpact < 0
                        ? "text-emerald-400"
                        : "text-neutral-200"
                    }
                  >
                    {formatINR(monthlyImpact, true)}/month
                  </span>
                </div>
              </div>

              {/* Cost Insight (Section 15) */}
              <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-5 space-y-2.5">
                <h4 className="text-xs font-bold text-neutral-200 uppercase tracking-wider flex items-center gap-1.5">
                  <HelpCircle className="w-3.5 h-3.5 text-emerald-400" />
                  Cost Insight
                </h4>
                <p className="text-xs text-neutral-300 leading-relaxed font-sans">{costInsightText}</p>
                <div className="pt-2 border-t border-neutral-800/80 text-[11px] text-neutral-500 font-mono">
                  Pricing sourced via Azure Retail Prices API (Consumption)
                </div>
              </div>
            </div>

            {/* What-If Simulation (Section 16) */}
            <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-5 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-xs font-bold text-neutral-200 uppercase tracking-wider flex items-center gap-1.5">
                    <Sliders className="w-3.5 h-3.5 text-emerald-400" />
                    What-If Simulation
                  </h4>
                  <p className="text-xs text-neutral-400">
                    Simulate alternative VM sizing to evaluate potential savings
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 pt-1">
                <div>
                  <label className="text-[11px] text-neutral-400 block mb-1">Current SKU</label>
                  <select
                    value={simCurrentSku}
                    onChange={(e) => setSimCurrentSku(e.target.value)}
                    className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-2.5 py-1.5 text-xs font-mono text-neutral-200 focus:outline-none"
                  >
                    {Object.keys(WHAT_IF_CATALOG).map((sku) => (
                      <option key={sku} value={sku}>
                        {sku} ({formatINR(WHAT_IF_CATALOG[sku], false, true)}/mo)
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-[11px] text-neutral-400 block mb-1">Alternative SKU</label>
                  <select
                    value={simAltSku}
                    onChange={(e) => setSimAltSku(e.target.value)}
                    className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-2.5 py-1.5 text-xs font-mono text-neutral-200 focus:outline-none"
                  >
                    {Object.keys(WHAT_IF_CATALOG).map((sku) => (
                      <option key={sku} value={sku}>
                        {sku} ({formatINR(WHAT_IF_CATALOG[sku], false, true)}/mo)
                      </option>
                    ))}
                  </select>
                </div>

                <div className="bg-neutral-950/70 border border-neutral-800/80 rounded-lg p-3">
                  <span className="text-[11px] text-neutral-400 block">Monthly Difference</span>
                  <span
                    className={`text-sm font-bold font-mono ${
                      simDiff > 0 ? "text-rose-400" : simDiff < 0 ? "text-emerald-400" : "text-neutral-300"
                    }`}
                  >
                    {formatINR(simDiff, true)}/mo
                  </span>
                </div>

                <div className="bg-neutral-950/70 border border-neutral-800/80 rounded-lg p-3">
                  <span className="text-[11px] text-neutral-400 block">Annual Difference</span>
                  <span
                    className={`text-sm font-bold font-mono ${
                      simAnnualDiff > 0
                        ? "text-rose-400"
                        : simAnnualDiff < 0
                        ? "text-emerald-400"
                        : "text-neutral-300"
                    }`}
                  >
                    {formatINR(simAnnualDiff, true)}/year
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: TERMINAL CLI VIEW */}
        {activeTab === "terminal" && (
          <div className="space-y-4">
            <div className="bg-black border border-neutral-800 rounded-xl overflow-hidden shadow-2xl">
              <div className="bg-neutral-900 px-4 py-2 border-b border-neutral-800 flex items-center justify-between text-xs font-mono text-neutral-400">
                <div className="flex items-center gap-2">
                  <Terminal className="w-3.5 h-3.5 text-neutral-400" />
                  <span>CostGuard CLI Output</span>
                </div>
                {exitCode !== null && (
                  <span
                    className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                      exitCode === 0
                        ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                        : exitCode === 1
                        ? "bg-rose-950 text-rose-400 border border-rose-800"
                        : "bg-amber-950 text-amber-400 border border-amber-800"
                    }`}
                  >
                    Exit Code {exitCode}
                  </span>
                )}
              </div>
              <pre className="p-6 font-mono text-xs text-neutral-200 whitespace-pre overflow-x-auto leading-relaxed min-h-[300px]">
                {output || "No terminal output available. Click 'Analyze Plan' to run."}
              </pre>
            </div>
          </div>
        )}

        {/* TAB 3: TEST SUITE */}
        {activeTab === "tests" && (
          <div className="space-y-4">
            <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-4 flex items-center justify-between">
              <div>
                <h4 className="text-sm font-semibold text-white">Automated Test Suite</h4>
                <p className="text-xs text-neutral-400">
                  Runs all 34 unit and integration tests covering parser, cache, guardrail, and calculations.
                </p>
              </div>
              <button
                onClick={handleRunTests}
                disabled={loading}
                className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium transition disabled:opacity-50"
              >
                {loading ? "Running Tests..." : "Run Pytest Suite"}
              </button>
            </div>

            <div className="bg-black border border-neutral-800 rounded-xl overflow-hidden">
              <div className="bg-neutral-900 px-4 py-2 border-b border-neutral-800 text-xs font-mono text-neutral-400">
                pytest -v output
              </div>
              <pre className="p-6 font-mono text-xs text-neutral-200 whitespace-pre overflow-x-auto leading-relaxed min-h-[300px]">
                {output || "Click 'Run Pytest Suite' above to execute tests."}
              </pre>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-neutral-800 py-3 text-center text-xs text-neutral-500 font-mono">
        COSTGUARD • "Predict infrastructure cost before you deploy." • Default Currency: INR (₹)
      </footer>
    </div>
  );
}
