import Image from "next/image";

import { SetupForm } from "./setup-form";
import setupArt from "../../../ChatGPT Image May 24, 2026, 02_51_39 PM.png";

export default function SetupPage() {
  return (
    <main className="min-h-screen w-full bg-[#fcf7f0]">
      <div className="mx-auto max-w-5xl px-6 pb-20 pt-24 sm:px-10 sm:pt-28 md:px-14 md:pt-32 lg:px-20">
        <section className="scroll-mt-8">
          <div className="grid grid-cols-1 items-start gap-x-10 gap-y-12 md:grid-cols-[minmax(0,0.4fr)_minmax(0,0.6fr)] md:gap-x-28 lg:gap-x-36">
            <div className="relative hidden min-h-[640px] md:block">
              <Image
                src={setupArt}
                alt="Illustration for setting up your voice agent"
                className="absolute left-1/2 top-[58%] h-auto w-[148%] max-w-none -translate-x-1/2 -translate-y-1/2 object-contain"
                priority
              />
            </div>
            <div
              className="min-w-0 space-y-10 text-[17px] leading-[1.65] text-neutral-900 md:text-lg"
              style={{
                fontFamily:
                  '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
              }}
            >
              <div className="max-w-xl space-y-6">
                <div className="flex justify-center pb-2 md:hidden">
                  <Image
                    src={setupArt}
                    alt="Illustration for setting up your voice agent"
                    className="h-auto w-full max-w-[26rem] object-contain"
                    priority
                  />
                </div>
                <p
                  className="text-[13px] tracking-[0.02em] text-neutral-500 md:text-[15px]"
                  style={{
                    fontFamily:
                      'var(--font-inter), -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
                  }}
                >
                  Setup
                </p>
                <h1 className="text-xl font-normal leading-snug text-neutral-600 md:text-2xl lg:text-[1.65rem]">
                  Set up your voice agent.
                </h1>
                <p className="text-neutral-700">
                  Fill in your details and we&apos;ll configure your agent and send the test number on WhatsApp.
                </p>
              </div>

              <SetupForm />
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
