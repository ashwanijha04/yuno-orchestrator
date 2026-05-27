"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { AgentForm, emptyAgent, type AgentFormValue } from "@/components/agent-form";

export default function NewAgentPage() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(v: AgentFormValue) {
    setSubmitting(true);
    setError(null);
    try {
      const agent = await api.createAgent(v);
      router.push(`/agents/${agent.id}`);
    } catch (e) {
      setError(String(e));
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">New agent</h1>
      <AgentForm initial={emptyAgent()} isNew onSubmit={submit} submitting={submitting} error={error} />
    </div>
  );
}
