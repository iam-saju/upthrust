"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";

type FormState = {
  name: string;
  businessName: string;
  mail: string;
  phone: string;
  aim: string;
};

const initialForm: FormState = {
  name: "",
  businessName: "",
  mail: "",
  phone: "",
  aim: "",
};

function isComplete(form: FormState) {
  return Object.values(form).every((value) => value.trim().length > 0);
}

export function SetupForm() {
  const router = useRouter();
  const [form, setForm] = useState<FormState>(initialForm);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const updateField = (field: keyof FormState, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
    if (error) setError("");
  };

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!isComplete(form)) {
      setError("Please fill all four fields.");
      return;
    }

    setSubmitting(true);
    setError("");

    try {
      const response = await fetch("/api/setup", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(form),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.error || `Server error ${response.status}.`);
      }

      router.push(`/setup/success?business=${encodeURIComponent(form.businessName.trim())}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error.";
      setError(message === "Setup request failed." ? "Airtable rejected the submission. Check field names match the base schema." : message);
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-xl space-y-5">
      <label className="setup-field">
        <span>Your name</span>
        <input
          required
          type="text"
          value={form.name}
          onChange={(event) => updateField("name", event.target.value)}
          autoComplete="name"
        />
      </label>

      <label className="setup-field">
        <span>Business name</span>
        <input
          required
          type="text"
          value={form.businessName}
          onChange={(event) => updateField("businessName", event.target.value)}
          autoComplete="organization"
        />
      </label>

      <label className="setup-field">
        <span>Email</span>
        <input
          required
          type="email"
          value={form.mail}
          onChange={(event) => updateField("mail", event.target.value)}
          autoComplete="email"
        />
      </label>

      <label className="setup-field">
        <span>Phone number</span>
        <input
          required
          type="tel"
          value={form.phone}
          onChange={(event) => updateField("phone", event.target.value)}
          autoComplete="tel"
          inputMode="tel"
        />
      </label>

      <label className="setup-field">
        <span>What does your business do?</span>
        <input
          required
          type="text"
          value={form.aim}
          onChange={(event) => updateField("aim", event.target.value)}
        />
      </label>
      {error && <p className="text-[14px] leading-6 text-[#9b3422]">{error}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="group inline-flex items-center gap-2 rounded-sm border-[1.5px] border-[#1a1a1a] bg-[#1a1a1a] px-5 py-2.5 text-[14px] text-white transition-all duration-200 hover:bg-[#111] hover:border-[#111] focus:outline-none disabled:cursor-not-allowed disabled:opacity-55"
      >
        {submitting ? "Creating..." : "Create My Agent"}
        <span aria-hidden className="transition-transform group-hover:translate-x-0.5">
          →
        </span>
      </button>
    </form>
  );
}
