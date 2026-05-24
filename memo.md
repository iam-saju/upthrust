# Buoyancy Labs Memo

## Overview

Buoyancy Labs is building voice AI agents for Indian businesses.

The core belief is that customer support should feel local, fast, human, and operationally useful, even when software is handling the conversation. Most current voice systems are built around clean English, rigid scripts, and generic support flows. Buoyancy Labs is building for the way people in India actually speak: mixed language, informal phrasing, strong local context, interruptions, half-sentences, and practical customer intent.

This is not just a chatbot product. It is a voice operations layer for businesses that rely on WhatsApp, inbound calls, and high-volume support conversations.

## The Product

The first live system is `RA-1`, Buoyancy Labs’ own inbound customer support agent.

RA-1 runs on the company’s WhatsApp number and handles inbound users directly. It is both:

- a working internal support operator
- a live product demo
- a dogfood system for the platform being built

When a user messages or sends a voice note to the WhatsApp number, RA-1:

- greets them
- identifies itself as a Buoyancy Labs customer support agent
- checks whether they are already known
- answers product questions
- qualifies new leads
- collects business details
- stores lead information in Airtable
- closes with a 24-hour follow-up promise

The product is effectively selling itself by being the product.

## What Is Being Built Right Now

The current system already includes the foundations of a real production voice agent:

- WhatsApp webhook ingestion through Meta
- support for both text and voice-note input
- Sarvam STT for transcription
- Sarvam TTS for audio replies
- deterministic conversation state orchestration
- in-memory per-caller session state
- Airtable lookup and waitlist storage
- LLM-based reply rendering
- latency instrumentation across the message pipeline

This means the system is evolving beyond “prompt + bot” into a layered conversational runtime.

## System Architecture

The emerging architecture has these layers:

### 1. Transport Layer

Handles:

- Meta WhatsApp webhook events
- inbound text/audio message parsing
- outbound text replies
- outbound audio uploads and sends

### 2. Speech Layer

Handles:

- speech-to-text using Sarvam
- text-to-speech using Sarvam

### 3. State and Orchestration Layer

Handles:

- caller session state
- deterministic conversation flow
- lead qualification stages
- returning-caller recognition
- structured conversation decisions

### 4. Memory Layer

Handles:

- short-term in-memory session state
- Airtable as lightweight CRM / waitlist memory

### 5. Rendering Layer

Handles:

- turning structured behavior plans into natural customer-facing language
- matching the caller’s language and tone
- keeping responses short, safe, and on-brand

### 6. Safety and Reliability Layer

Handles:

- deterministic fallbacks
- output validation
- planner-language blocking
- latency measurement

## Product Direction

The long-term product is bigger than RA-1.

RA-1 is the first operator, but the real goal is to build a reusable platform for customer support voice agents that Indian businesses can deploy quickly.

That means Buoyancy Labs aims to become the voice support layer for:

- shops
- pharmacies
- logistics businesses
- D2C brands
- growing consumer platforms

The platform should allow these businesses to handle:

- order status questions
- delivery updates
- payment confirmations
- complaints
- callbacks
- onboarding questions
- lead qualification
- high-volume repetitive support flows

without needing a human to manually handle every interaction.

## What Makes Buoyancy Different

The differentiation is not “we have AI voice.”

The differentiation is:

- built for Indian language mixing
- built for Indian customer behavior
- built for operational support, not just FAQ bots
- built for WhatsApp and voice-first usage
- built to sound like a competent support operator, not a robotic assistant

Most systems are still:

- English-first
- script-heavy
- brittle
- enterprise-integration-heavy

Buoyancy’s advantage is speed, localness, and operational realism.

## Product Philosophy

The product philosophy is moving toward a strong architecture:

- the application should be the brain
- the LLM should not control workflow
- the LLM should only render natural language
- behavior should be deterministic where reliability matters
- personality should be designed, not improvised
- fallbacks should be intentional, safe, and branded

This matters because production conversational systems fail when the model is allowed to own too much control.

So the direction is:

- deterministic orchestration
- structured behavior planning
- safe language rendering
- measurable latency
- explicit recovery behavior

## Current Challenges

The main challenges being worked through right now are:

- making RA-1 sound like a real support operator instead of a generic assistant
- removing instruction leakage from internal planner language
- improving fallback quality
- tightening identity and personality consistency
- ensuring WhatsApp send/auth is reliable
- making Airtable integration stable
- diagnosing Sarvam LLM response parsing issues
- lowering voice-turn latency

These are normal problems for a system moving from prototype behavior to production-grade conversational architecture.

## What Success Looks Like

A successful Buoyancy Labs agent should:

- answer quickly
- sound local and human
- understand mixed language usage
- collect useful business information automatically
- recognize returning users
- stay on-task
- recover gracefully from ambiguity
- keep support flows structured
- reduce manual support effort
- feel like a competent operations associate, not a chatbot

At the business level, success means:

- inbound interest is automatically qualified
- customer support scales without a proportional support headcount increase
- businesses can go live quickly
- the architecture used internally can be turned into a product for customers

## Product Vision

Buoyancy Labs is building the voice support infrastructure for Indian businesses.

Not just bots.
Not just prompts.
Not just speech APIs.

But a full conversational operations layer that can listen, respond, qualify, remember, recover, and sound natural in real support situations.

The long-term vision is that any business should be able to plug in a Buoyancy agent and instantly get a support operator that:

- speaks the customer’s language
- understands context
- handles repetitive operations reliably
- sounds sharp, practical, and trustworthy

## One-Line Vision

Buoyancy Labs is building multilingual voice support agents for Indian businesses that feel local, human, and operationally useful from day one.
