import Image from "next/image";
import { LabSection } from "@/components/lab-section";
import { VoiceTyping } from "@/components/voice-typing";
import { SupportLog } from "@/components/support-log";

export default function Home() {
  return (
    <>
      <main className="flex-1 w-full bg-white">
{/* ── About ──────────────────────────────────────────── */}
        <div className="max-w-5xl mx-auto px-6 sm:px-10 md:px-14 lg:px-20 pt-28 sm:pt-36 md:pt-44 pb-16 md:pb-20">
          <LabSection id="belief" label="Our Belief">
            <div>
              <h1 className="text-xl md:text-2xl lg:text-[1.65rem] font-normal text-neutral-600 leading-snug max-w-xl">
                Support should sound like
                <br className="md:hidden" />
                {" "}your{" "}
                <VoiceTyping
                  words={[
                    "shopkeeper",
                    "दुकानदार",
                    "கடைக்காரர்",
                    "দোকানদার",
                    "കടക്കാരൻ",
                    "friend",
                    "दोस्त",
                    "நண்பா",
                    "বন্ধு",
                    "സുഹൃത്ത്",
                    "cousin",
                    "भाई",
                    "அண்ணா",
                    "দাদা",
                    "ചേട്ടാ",
                  ]}
                  className="voice-layer--inline voice-layer--accent"
                />
                <br />
                picked up the{" "}
                <span className="brand-accent text-neutral-950">call</span>.
              </h1>
              <div className="max-w-xl space-y-6">
                <p>
                  At{" "}
                  <strong className="font-medium text-neutral-950">
                    Buoyancy Labs
                  </strong>
                  , we are building voice AI that understands how Indians
                  actually speak — the mixed language, the shortcuts, the
                  warmth, and the pauses.
                </p>
              </div>
            </div>
          </LabSection>
        </div>

        {/* ── Documentary image ────────────────────────────────── */}
        <div className="max-w-5xl mx-auto px-6 sm:px-10 md:px-14 lg:px-20">
          <div className="grid grid-cols-1 md:grid-cols-[minmax(0,0.28fr)_minmax(0,0.72fr)] gap-x-10 md:gap-x-14 lg:gap-x-24">
            <div className="hidden md:block" />
            <div className="documentary-frame relative w-full max-w-xl aspect-4/3 md:aspect-3/2 overflow-hidden bg-neutral-200">
              <Image
                src="/638c71eff00d022cb71a07ad743f2234.jpg"
                alt="Impressionistic oil painting of a bustling South Asian street market with vendors and shoppers"
                fill
                className="object-cover object-center documentary-img"
                sizes="(max-width: 768px) 100vw, 36rem"
                preload
              />

            </div>
          </div>
        </div>

        {/* ── Agents + Mission ────────────────────────────────── */}
        <div className="max-w-5xl mx-auto px-6 sm:px-10 md:px-14 lg:px-20 pt-20 md:pt-28 pb-12 md:pb-16">
          <LabSection id="agents" label="Our Agents">
            <div>
              <div className="max-w-xl space-y-6">
                <p>
                  Our agents are built for the calls Indian businesses receive
                  every day — order questions, payment confirmations, complaints,
                  callbacks, and small doubts.
                </p>
              </div>
              <SupportLog />
              <div className="max-w-xl space-y-2 text-neutral-800 pt-6">
                <p>No stiff scripts.</p>
                <p>No awkward translations.</p>
                <p>Just a voice that knows how to respond.</p>
              </div>
            </div>
          </LabSection>

          <LabSection id="mission" label="The Mission">
            <div className="max-w-xl space-y-6">
              <p>
                We want every customer to feel heard in the language they trust.
              </p>
              <p>
                When support feels familiar, a business stops feeling distant.
              </p>
              <div className="space-y-1.5 text-neutral-800">
                <p>This is more than AI.</p>
                <p>
                  <strong className="font-medium text-neutral-950">
                    This is Buoyancy.
                  </strong>
                </p>
                <p>A new voice layer for Indian businesses.</p>
              </div>
              <div className="flex flex-col gap-7 pt-4 items-start sm:flex-row sm:items-center">
                <a
                  href="https://airtable.com/app2EGU9ub0BLp6Oc/pagsJL8j96QTLjXCC/form"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group inline-flex items-center gap-2 bg-transparent border border-black/14 text-[#111] rounded-sm py-3.5 px-5.5 text-[14px] transition-all duration-200 hover:bg-[#111] hover:text-[#f5f5f5] hover:border-[#111] focus:outline-none"
                >
                  Request demo access
                  <span
                    aria-hidden
                    className="transition-transform group-hover:translate-x-0.5"
                  >
                    →
                  </span>
                </a>
                <a
                  href="mailto:hello@buoyancylabs.example"
                  className="group inline-flex items-center gap-2 text-[14px] text-neutral-500/65 transition-all duration-200 hover:text-neutral-900 hover:translate-x-0.5 focus:outline-none"
                >
                  Get in touch
                  <span
                    aria-hidden
                    className="transition-transform group-hover:translate-x-0.5"
                  >
                    →
                  </span>
                </a>
              </div>
            </div>
          </LabSection>
        </div>
      </main>
    </>
  );
}
