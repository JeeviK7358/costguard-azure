import express from "express";
import { exec, spawn } from "child_process";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { createServer as createViteServer } from "vite";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function startServer() {
  const app = express();
  const PORT = Number(process.env.PORT) || 3000;

  app.use(express.json({ limit: "10mb" }));

  // API Route: list available sample test plans
  app.get("/api/test-plans", (req, res) => {
    try {
      const plansDir = path.join(__dirname, "test-plans");
      const files = ["plan-create.json", "plan-delete.json", "plan-update.json", "plan-noise.json"];
      const plans = files.map((file) => {
        const filePath = path.join(plansDir, file);
        const content = fs.existsSync(filePath) ? fs.readFileSync(filePath, "utf-8") : "{}";
        return {
          id: file,
          name: file.replace(".json", ""),
          content,
        };
      });
      res.json({ plans });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // API Route: Run CostGuard CLI analysis
  app.post("/api/analyze", async (req, res) => {
    try {
      const { plan_json, max_increase, currency = "INR" } = req.body;

      if (!plan_json || typeof plan_json !== "string") {
        return res.status(400).json({ error: "Missing or invalid plan_json" });
      }

      // Create a temporary plan file
      const tempPlanPath = path.join("/tmp", `costguard_plan_${Date.now()}.json`);
      fs.writeFileSync(tempPlanPath, plan_json, "utf-8");

      const args = ["-m", "costguard", "--plan", tempPlanPath, "--currency", currency];
      if (max_increase !== undefined && max_increase !== null && max_increase !== "") {
        args.push("--max-increase", String(max_increase));
      }

      // Also generate JSON for structured data
      const jsonArgs = [...args, "--json"];

      // Run terminal formatted version
      const runProcess = (cmdArgs: string[]): Promise<{ stdout: string; stderr: string; code: number }> => {
        return new Promise((resolve) => {
          const proc = spawn("python3", cmdArgs, {
            env: { ...process.env, PYTHONUNBUFFERED: "1", TERM: "xterm-256color" },
          });

          let stdout = "";
          let stderr = "";

          proc.stdout.on("data", (data) => {
            stdout += data.toString();
          });

          proc.stderr.on("data", (data) => {
            stderr += data.toString();
          });

          proc.on("close", (code) => {
            resolve({ stdout, stderr, code: code ?? 0 });
          });

          proc.on("error", (err) => {
            stderr += err.message;
            resolve({ stdout, stderr, code: 2 });
          });
        });
      };

      const terminalResult = await runProcess(args);
      const jsonResult = await runProcess(jsonArgs);

      // Clean up temp plan file
      try {
        if (fs.existsSync(tempPlanPath)) {
          fs.unlinkSync(tempPlanPath);
        }
      } catch {
        // ignore cleanup error
      }

      let parsedJson: any = null;
      try {
        parsedJson = JSON.parse(jsonResult.stdout);
      } catch {
        // parsing might fail if input was bad or exited with error
      }

      res.json({
        exitCode: terminalResult.code,
        terminalOutput: terminalResult.stdout,
        errorOutput: terminalResult.stderr,
        report: parsedJson,
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // API Route: Inspect cache
  app.get("/api/cache", (req, res) => {
    exec(
      `python3 -c "import sqlite3, json; conn = sqlite3.connect('pricing_cache.db'); conn.row_factory = sqlite3.Row; rows = [dict(r) for r in conn.execute('SELECT * FROM pricing_cache ORDER BY cached_at DESC LIMIT 50').fetchall()]; print(json.dumps(rows))"`,
      (err, stdout) => {
        if (err) {
          return res.json({ rows: [] });
        }
        try {
          const rows = JSON.parse(stdout || "[]");
          res.json({ rows });
        } catch {
          res.json({ rows: [] });
        }
      }
    );
  });

  // API Route: Clear cache
  app.post("/api/clear-cache", (req, res) => {
    exec("costguard --clear-cache", (err, stdout, stderr) => {
      res.json({
        success: !err,
        output: stdout || stderr,
      });
    });
  });

  // API Route: Run pytest
  app.post("/api/run-tests", (req, res) => {
    exec("pytest -v", (err, stdout, stderr) => {
      res.json({
        exitCode: err ? (err.code ?? 1) : 0,
        output: stdout || stderr,
      });
    });
  });

  // Vite middleware in dev
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    // Serve static files in production
    app.use(express.static(path.join(__dirname, "dist")));
    app.get("*", (req, res) => {
      res.sendFile(path.join(__dirname, "dist", "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`CostGuard Server running on port ${PORT}`);
  });
}

startServer();
