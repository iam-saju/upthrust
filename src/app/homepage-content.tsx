"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";

import { SupportLog } from "@/components/support-log";
import { VoiceTyping } from "@/components/voice-typing";
import heroMarketImage from "../../public/638c71eff00d022cb71a07ad743f2234.jpg";

type ThemeMode = "system" | "light" | "dark";
type ResolvedTheme = "light" | "dark";
type LanguageCode = "en" | "hi" | "ta" | "ml";

const THEME_KEY = "buoyancy-theme";
const LANGUAGE_KEY = "buoyancy-language";

const LANGUAGES: Array<{ code: LanguageCode; label: string; nativeLabel: string }> = [
  { code: "en", label: "English", nativeLabel: "English" },
  { code: "hi", label: "Hindi", nativeLabel: "हिन्दी" },
  { code: "ta", label: "Tamil", nativeLabel: "தமிழ்" },
  { code: "ml", label: "Malayalam", nativeLabel: "മലയാളം" },
];

const COPY: Record<LanguageCode, {
  belief: string;
  heroTitle: string;
  heroBody: string;
  agents: string;
  agentsIntro: string;
  shopsTitle: string;
  shopsBody: string;
  platformsTitle: string;
  platformsBody: string;
  noScripts: string;
  noTranslations: string;
  noSprints: string;
  indianScale: string;
  requestDemo: string;
  mission: string;
  missionLines: string[];
  getInTouch: string;
  controls: {
    system: string;
    light: string;
    dark: string;
    language: string;
  };
}> = {
  en: {
    belief: "Our Belief",
    heroTitle: "Support should sound like your",
    heroBody:
      "At Buoyancy Labs, we build voice agents that understand how Indians actually speak — the mixed language, the shortcuts, the warmth, and the pauses. Not translated. Not approximated. Understood.",
    agents: "Our Agents",
    agentsIntro:
      "Indian businesses get customer calls every day.\n\nOur agents are built to handle them.",
    shopsTitle: "For shops and small businesses",
    shopsBody:
      "Orders, payments, complaints, and callbacks in the language your customer speaks.",
    platformsTitle: "For growing platforms",
    platformsBody:
      "Payment failures, delivery issues, support spikes, and backlog handling at scale.",
    noScripts: "No stiff scripts.",
    noTranslations: "No awkward translations.",
    noSprints: "",
    indianScale: "Voice that works at Indian scale.",
    requestDemo: "Request demo",
    mission: "The Mission",
    missionLines: [
      "Every caller deserves to feel understood.",
      "Not on hold. Not transferred. Not answered in the wrong language.",
      "We build voice agents for how India actually speaks.",
      "This is Buoyancy.",
    ],
    getInTouch: "Get in touch",
    controls: {
      system: "System",
      light: "Light",
      dark: "Dark",
      language: "Language",
    },
  },
  hi: {
    belief: "हमारा विश्वास",
    heroTitle: "भारत जिस तरह सच में बोलता है, उसी के लिए बनाया गया.",
    heroBody:
      "Buoyancy Labs ऐसे वॉयस एजेंट बनाता है जो मिली-जुली भाषा, स्थानीय संदर्भ और वे छोटे मानवीय संकेत समझते हैं जिन्हें अधिकतर सिस्टम छोड़ देते हैं.",
    agents: "हमारे एजेंट",
    agentsIntro: "हमारे एजेंट भारतीय व्यवसायों को रोज आने वाली असली कॉल्स के लिए बने हैं.",
    shopsTitle: "दुकानों और छोटे व्यवसायों के लिए",
    shopsBody: "ऑर्डर के सवाल, पेमेंट रिमाइंडर, शिकायतें और कॉलबैक.",
    platformsTitle: "बढ़ते प्लेटफॉर्म्स के लिए",
    platformsBody: "पेमेंट फेलियर, डिलीवरी अपवाद, सपोर्ट स्पाइक और बैकलॉग संभालना.",
    noScripts: "कोई कठोर स्क्रिप्ट नहीं.",
    noTranslations: "कोई अटपटा अनुवाद नहीं.",
    noSprints: "छह महीने की इंटीग्रेशन दौड़ नहीं.",
    indianScale: "बस ऐसी आवाज़ जो भारतीय स्केल पर काम करे.",
    requestDemo: "डेमो मांगें",
    mission: "मिशन",
    missionLines: [
      "भारत परफेक्ट वाक्यों में नहीं बोलता.",
      "यह भाव, शॉर्टकट और संदर्भ में बोलता है.",
      "हमारा मिशन सरल है:",
      "ऐसे वॉयस एजेंट बनाना जो भारत को जैसा है वैसा समझें.",
    ],
    getInTouch: "संपर्क करें",
    controls: {
      system: "सिस्टम",
      light: "लाइट",
      dark: "डार्क",
      language: "भाषा",
    },
  },
  ta: {
    belief: "எங்கள் நம்பிக்கை",
    heroTitle: "இந்தியா உண்மையில் பேசும் முறைக்காக உருவாக்கப்பட்டது.",
    heroBody:
      "Buoyancy Labs கலந்த மொழி, உள்ளூர் சூழல், பெரும்பாலான அமைப்புகள் தவறவிடும் சிறிய மனித சைகைகள் ஆகியவற்றைப் புரியும் voice agents-ஐ உருவாக்குகிறது.",
    agents: "எங்கள் முகவர்கள்",
    agentsIntro: "இந்திய வணிகங்களுக்கு தினமும் வரும் உண்மையான calls-க்காக எங்கள் agents உருவாக்கப்பட்டுள்ளன.",
    shopsTitle: "கடைகள் மற்றும் சிறு வணிகங்களுக்கு",
    shopsBody: "Order கேள்விகள், payment reminders, complaints, callbacks.",
    platformsTitle: "வளரும் platforms-க்காக",
    platformsBody: "Payment failures, delivery exceptions, support spikes, backlog handling.",
    noScripts: "கட்டுப்பட்ட scripts இல்லை.",
    noTranslations: "சிரமமான translations இல்லை.",
    noSprints: "ஆறு மாத integration sprints இல்லை.",
    indianScale: "இந்திய அளவில் இயங்கும் இயல்பான voice மட்டும்.",
    requestDemo: "டெமோ கேட்கவும்",
    mission: "மிஷன்",
    missionLines: [
      "இந்தியா முழுமையான வாக்கியங்களில் பேசுவதில்லை.",
      "அது உணர்வு, shortcuts, context-ல் பேசுகிறது.",
      "எங்கள் mission எளிது:",
      "இந்தியாவை அது இருப்பது போலப் புரியும் voice agents உருவாக்குவது.",
    ],
    getInTouch: "தொடர்பு கொள்ளுங்கள்",
    controls: {
      system: "சிஸ்டம்",
      light: "லைட்",
      dark: "டார்க்",
      language: "மொழி",
    },
  },
  ml: {
    belief: "ഞങ്ങളുടെ വിശ്വാസം",
    heroTitle: "ഇന്ത്യ യഥാർത്ഥത്തിൽ സംസാരിക്കുന്ന രീതിക്കായി നിർമ്മിച്ചത്.",
    heroBody:
      "Buoyancy Labs mixed language, local context, മിക്ക systems-ും കാണാതെ പോകുന്ന ചെറിയ human signals എന്നിവ മനസ്സിലാക്കുന്ന voice agents സൃഷ്ടിക്കുന്നു.",
    agents: "ഞങ്ങളുടെ ഏജന്റുകൾ",
    agentsIntro: "ഇന്ത്യൻ businesses-ന് ദിവസവും വരുന്ന യഥാർത്ഥ calls-ിനായാണ് ഞങ്ങളുടെ agents നിർമ്മിച്ചിരിക്കുന്നത്.",
    shopsTitle: "കടകൾക്കും ചെറിയ businesses-നും",
    shopsBody: "Order questions, payment reminders, complaints, callbacks.",
    platformsTitle: "വളരുന്ന platforms-ക്കായി",
    platformsBody: "Payment failures, delivery exceptions, support spikes, backlog handling.",
    noScripts: "കട്ടിയുള്ള scripts ഇല്ല.",
    noTranslations: "അസൗകര്യമായ translations ഇല്ല.",
    noSprints: "ആറ് മാസം നീളുന്ന integration sprints ഇല്ല.",
    indianScale: "ഇന്ത്യൻ scale-ൽ പ്രവർത്തിക്കുന്ന സ്വാഭാവിക voice മാത്രം.",
    requestDemo: "ഡെമോ അഭ്യർത്ഥിക്കുക",
    mission: "മിഷൻ",
    missionLines: [
      "ഇന്ത്യ perfect sentences-ൽ സംസാരിക്കുന്നില്ല.",
      "അത് feelings, shortcuts, context എന്നിവയിൽ സംസാരിക്കുന്നു.",
      "ഞങ്ങളുടെ mission simple ആണ്:",
      "ഇന്ത്യയെ അതുപോലെ മനസ്സിലാക്കുന്ന voice agents നിർമ്മിക്കുക.",
    ],
    getInTouch: "ബന്ധപ്പെടുക",
    controls: {
      system: "സിസ്റ്റം",
      light: "ലൈറ്റ്",
      dark: "ഡാർക്ക്",
      language: "ഭാഷ",
    },
  },
};

function ThemeIcon({ mode }: { mode: ThemeMode }) {
  if (mode === "system") {
    return (
      <svg
        className="preference-icon preference-icon--monitor"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <rect x="4" y="5" width="16" height="11" rx="1.8" />
        <path d="M9 20h6" />
        <path d="M12 16v4" />
      </svg>
    );
  }

  if (mode === "light") {
    return (
      <svg
        className="preference-icon preference-icon--sun"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2.8v2.4" />
        <path d="M12 18.8v2.4" />
        <path d="M4.2 4.2l1.7 1.7" />
        <path d="M18.1 18.1l1.7 1.7" />
        <path d="M2.8 12h2.4" />
        <path d="M18.8 12h2.4" />
        <path d="M4.2 19.8l1.7-1.7" />
        <path d="M18.1 5.9l1.7-1.7" />
      </svg>
    );
  }

  return (
    <svg
      className="preference-icon preference-icon--moon"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path d="M19.5 15.2A8.2 8.2 0 0 1 8.8 4.5 8.6 8.6 0 1 0 19.5 15.2Z" />
    </svg>
  );
}

function GlobeIcon() {
  return (
    <svg
      className="preference-icon preference-icon--globe"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="8.6" />
      <path d="M3.8 12h16.4" />
      <path d="M12 3.4c2.3 2.3 3.4 5.2 3.4 8.6S14.3 18.3 12 20.6" />
      <path d="M12 3.4C9.7 5.7 8.6 8.6 8.6 12s1.1 6.3 3.4 8.6" />
    </svg>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className="preference-icon preference-icon--chevron"
      viewBox="0 0 24 24"
      aria-hidden="true"
      data-open={open}
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

function getSystemTheme(): ResolvedTheme {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function resolveTheme(mode: ThemeMode): ResolvedTheme {
  return mode === "system" ? getSystemTheme() : mode;
}

function isThemeMode(value: string | null): value is ThemeMode {
  return value === "system" || value === "light" || value === "dark";
}

function isLanguageCode(value: string | null): value is LanguageCode {
  return value === "en" || value === "hi" || value === "ta" || value === "ml";
}

function getStoredThemeMode(): ThemeMode {
  if (typeof window === "undefined") return "system";
  const storedTheme = window.localStorage.getItem(THEME_KEY);
  return isThemeMode(storedTheme) ? storedTheme : "system";
}

function getStoredLanguage(): LanguageCode {
  if (typeof window === "undefined") return "en";
  const storedLanguage = window.localStorage.getItem(LANGUAGE_KEY);
  return isLanguageCode(storedLanguage) ? storedLanguage : "en";
}

function applyTheme(mode: ThemeMode, resolved: ResolvedTheme) {
  document.documentElement.dataset.themeMode = mode;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
}

export function HomepageContent() {
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => getStoredThemeMode());
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() =>
    resolveTheme(getStoredThemeMode()),
  );
  const [language, setLanguage] = useState<LanguageCode>(() => getStoredLanguage());
  const [languageOpen, setLanguageOpen] = useState(false);
  const languageRef = useRef<HTMLDivElement | null>(null);
  const t = COPY[language];
  const selectedLanguage = LANGUAGES.find((item) => item.code === language) ?? LANGUAGES[0];

  useEffect(() => {
    applyTheme(themeMode, resolvedTheme);
  }, [themeMode, resolvedTheme]);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");

    function handleSystemThemeChange() {
      if (themeMode !== "system") return;
      const nextResolvedTheme = resolveTheme("system");
      setResolvedTheme(nextResolvedTheme);
      applyTheme("system", nextResolvedTheme);
    }

    media.addEventListener("change", handleSystemThemeChange);
    return () => media.removeEventListener("change", handleSystemThemeChange);
  }, [themeMode]);

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      if (!languageRef.current?.contains(event.target as Node)) {
        setLanguageOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setLanguageOpen(false);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  function updateTheme(mode: ThemeMode) {
    const nextResolvedTheme = resolveTheme(mode);
    setThemeMode(mode);
    setResolvedTheme(nextResolvedTheme);
    localStorage.setItem(THEME_KEY, mode);
    applyTheme(mode, nextResolvedTheme);
  }

  function updateLanguage(nextLanguage: LanguageCode) {
    setLanguage(nextLanguage);
    localStorage.setItem(LANGUAGE_KEY, nextLanguage);
    setLanguageOpen(false);
  }

  return (
    <main className="homepage-main flex-1 w-full">
      <section className="homepage-hero">
        <div className="homepage-hero__shell">
          <p className="homepage-section__label">{t.belief}</p>
          <div className="homepage-hero__content">
            <div className="homepage-hero__copy">
              <h1
                className="homepage-hero__headline"
              >
                {language === "en" ? (
                  <>
                    <span className="homepage-hero__headline-strong">
                      Support should sound like your{" "}
                    </span>
                    <span className="homepage-hero__typing">
                      <VoiceTyping
                        words={[
                          "दोकानदार",
                          "shopkeeper",
                          "merchant",
                          "கடைக்காரர்",
                          "salesperson",
                          "കടക്കാരൻ",
                          "store owner",
                        ]}
                        className="voice-layer--inline voice-layer--accent"
                      />
                    </span>
                    <br />
                    picked up the <em className="homepage-hero__headline-call">call</em>.
                  </>
                ) : (
                  t.heroTitle
                )}
              </h1>
              <div className="homepage-hero__body-wrap max-w-xl space-y-6">
                <p className="homepage-copy">
                  {t.heroBody}
                </p>
              </div>
            </div>

            <div className="homepage-hero__visual">
              <div className="homepage-hero__frame">
                <Image
                  src={heroMarketImage}
                  alt="South Asian street market background for support conversations"
                  fill
                  className="homepage-hero__image"
                  sizes="(max-width: 768px) 100vw, 42rem"
                  quality={82}
                  priority
                />
              </div>
              <div className="homepage-hero__snippet">
                <SupportLog theme={resolvedTheme} />
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="homepage-sections-shell">
        <section id="agents" className="agents-section scroll-mt-8">
          <div className="agents-feature">
            <p className="homepage-section__label">{t.agents}</p>
            <div className="agents-feature__copy">
              <div className="agents-feature__intro max-w-xl">
                {t.agentsIntro.split("\n\n").map((paragraph) => (
                  <p key={paragraph}>{paragraph}</p>
                ))}
              </div>
              <div className="agents-feature__audiences max-w-xl">
                <div>
                  <p className="agents-feature__audience-title">{t.shopsTitle}</p>
                  <p>{t.shopsBody}</p>
                </div>
                <div>
                  <p className="agents-feature__audience-title">{t.platformsTitle}</p>
                  <p>{t.platformsBody}</p>
                </div>
              </div>
              <div className="agents-feature__points max-w-xl">
                <p>{t.noScripts}</p>
                <p>{t.noTranslations}</p>
                {t.noSprints && <p>{t.noSprints}</p>}
                <p>{t.indianScale}</p>
              </div>
              <div className="agents-feature__cta">
                <span className="agents-feature__cta-note">
                  You can test the demo via WhatsApp.
                </span>
                <a
                  href="/setup"
                  className="homepage-link inline-flex items-center gap-2 text-[14px] transition-colors duration-200 focus:outline-none"
                >
                  {t.requestDemo}
                  <span aria-hidden>→</span>
                </a>
              </div>
            </div>
          </div>
        </section>

        <section id="mission" className="mission-section scroll-mt-8">
          <div className="mission-feature">
            <p className="homepage-section__label">{t.mission}</p>
            <div className="mission-feature__copy">
              <div className="mission-feature__body max-w-xl">
                {t.missionLines.map((line) => (
                  <p key={line}>{line}</p>
                ))}
                <div className="mission-feature__cta flex flex-col gap-7 items-start sm:flex-row sm:items-center">
                  <a
                    href="mailto:iamsajubabu@gmail.com"
                    className="mission-feature__contact group inline-flex items-center gap-2 text-[14px] transition-all duration-200 hover:translate-x-0.5 focus:outline-none"
                  >
                    {t.getInTouch}
                    <span
                      aria-hidden
                      className="transition-transform group-hover:translate-x-0.5"
                    >
                      →
                    </span>
                  </a>
                </div>
              </div>
            </div>
          </div>
        </section>

        <div className="site-preferences" aria-label="Site preferences">
          <div className="theme-switch" role="group" aria-label="Theme">
            {(["system", "light", "dark"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                aria-label={t.controls[mode]}
                aria-pressed={themeMode === mode}
                className="theme-switch__button"
                data-active={themeMode === mode}
                onClick={() => updateTheme(mode)}
              >
                <ThemeIcon mode={mode} />
              </button>
            ))}
          </div>

          <div className="language-switch" ref={languageRef}>
            {languageOpen && (
              <div className="language-switch__menu" role="menu">
                {LANGUAGES.map((item) => (
                  <button
                    key={item.code}
                    type="button"
                    role="menuitemradio"
                    aria-checked={language === item.code}
                    className="language-switch__option"
                    onClick={() => updateLanguage(item.code)}
                  >
                    <span>{item.nativeLabel}</span>
                    {language === item.code && <span aria-hidden>✓</span>}
                  </button>
                ))}
              </div>
            )}
            <button
              type="button"
              className="language-switch__button"
              aria-label={t.controls.language}
              aria-expanded={languageOpen}
              onClick={() => setLanguageOpen((open) => !open)}
            >
              <GlobeIcon />
              <span>{selectedLanguage.nativeLabel}</span>
              <ChevronIcon open={languageOpen} />
            </button>
          </div>
        </div>
      </div>
    </main>
  );
}
