"use client";

import { useState } from "react";
import { apiClient } from "@/lib/api/client";
import { AgentStep } from "@/lib/types/api";

export default function AgentPlayground() {
  const [prompt, setPrompt] = useState("");
  const [system, setSystem] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [output, setOutput] = useState<string | null>(null);
  const [steps, setSteps] = useState<AgentStep[]>([]);

  const runAgent = async () => {
    if (!prompt.trim()) {
      setError("Please enter a prompt.");
      return;
    }
    setLoading(true);
    setError(null);
    setOutput(null);
    setSteps([]);

    try {
      const response = await apiClient.agents.run({
        prompt: prompt.trim(),
        system: system.trim() || undefined,
      });
      setOutput(response.output);
      setSteps(response.steps);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Agent run failed";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-indigo-50">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12 space-y-8">
        <header className="space-y-2">
          <p className="text-xs uppercase tracking-[0.3em] text-indigo-500 font-semibold">
            Agent playground
          </p>
          <h1 className="text-4xl font-bold text-gray-900 tracking-tight">Run an agent</h1>
          <p className="text-sm text-gray-700">
            Submit a prompt to the stubbed agent endpoint. Swap the provider in the backend to call
            your preferred LLM.
          </p>
        </header>

        <div className="bg-white shadow rounded-xl border border-indigo-50 p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-800 mb-1">Prompt</label>
            <textarea
              rows={4}
              className="w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 text-sm text-gray-900 bg-white"
              placeholder="Ask the agent to draft a message, summarize text, or outline a plan..."
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-800 mb-1">
              System guidance (optional)
            </label>
            <input
              type="text"
              className="w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 text-sm text-gray-900 bg-white"
              placeholder="e.g., Keep responses concise and actionable."
              value={system}
              onChange={(e) => setSystem(e.target.value)}
            />
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={runAgent}
              disabled={loading}
              className="px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-md hover:bg-indigo-700 disabled:bg-indigo-400"
            >
              {loading ? "Running..." : "Run agent"}
            </button>
            {error && <span className="text-sm text-red-600">{error}</span>}
          </div>
        </div>

        {steps.length > 0 && (
          <div className="bg-white shadow rounded-xl border border-indigo-50 p-6 space-y-4">
            <h2 className="text-lg font-semibold text-gray-900">Steps</h2>
            <div className="space-y-2">
              {steps.map((step, idx) => (
                <div
                  key={`${step.step_type}-${idx}`}
                  className="border border-gray-200 rounded-md p-3 bg-gray-50"
                >
                  <p className="text-xs uppercase tracking-[0.2em] text-gray-500 font-semibold">
                    {step.step_type}
                  </p>
                  <p className="text-sm text-gray-900 mt-1 whitespace-pre-wrap">{step.content}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {output && (
          <div className="bg-white shadow rounded-xl border border-indigo-50 p-6 space-y-2">
            <h2 className="text-lg font-semibold text-gray-900">Output</h2>
            <p className="text-sm text-gray-900 whitespace-pre-wrap">{output}</p>
          </div>
        )}
      </div>
    </div>
  );
}
