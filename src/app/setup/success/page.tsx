import Image from "next/image";

type SuccessPageProps = {
  searchParams: Promise<{
    business?: string;
  }>;
};

function formatMaskedTestNumber(phone: string) {
  const digits = phone.replace(/[^\d]/g, "");
  if (digits.startsWith("1555")) {
    return "+1 (555) ***  - ****";
  }
  return "a WhatsApp test number";
}

export default async function SetupSuccessPage({ searchParams }: SuccessPageProps) {
  const { business } = await searchParams;
  const businessName = business?.trim() || "your business";
  const whatsappNumber = process.env.NEXT_PUBLIC_RA1_WHATSAPP_NUMBER || "";
  const maskedTestNumber = formatMaskedTestNumber(whatsappNumber);

  return (
    <main className="min-h-screen w-full bg-[#fdfbf0]">
      <div className="mx-auto flex min-h-screen max-w-7xl items-center justify-center px-6 py-10 sm:px-10 md:px-14 lg:px-16">
        <section className="w-full">
          <div className="grid grid-cols-1 items-center gap-x-14 gap-y-10 md:grid-cols-2 lg:gap-x-20">
            <div className="min-w-0">
              <div className="relative mx-auto h-[66vh] w-full max-w-[720px] max-h-[900px] md:h-[74vh] md:max-w-[860px]">
                <Image
                  src="/setup-success-art-v2.png"
                  alt="Buoyancy Labs success artwork"
                  fill
                  className="object-contain object-center scale-[1.06]"
                  sizes="(max-width: 768px) 90vw, 50vw"
                  priority
                />
              </div>
            </div>
            <div
              className="min-w-0 self-center space-y-10 text-[16px] leading-7 text-neutral-900 md:text-[16px]"
              style={{
                fontFamily:
                  '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
              }}
            >
              <div className="max-w-xl space-y-6">
                <h1 className="text-xl font-normal leading-snug text-neutral-600 md:text-2xl lg:text-[1.65rem]">
                  Your voice agent is ready to configure.
                </h1>
                <p>
                  We&apos;ll have your voice agent set up for{" "}
                  <span className="font-medium text-neutral-950">{businessName}</span>.
                </p>
                <p className="text-neutral-700">
                  For this demo, setup and initiation will happen only through our temporary test number that will be like{" "}
                  <span className="ml-1 inline-flex rounded-full border border-black/10 bg-[#f6f6f3] px-3 py-1 text-[16px] font-medium leading-7 tracking-[0.02em] text-neutral-950">
                    +1 (555) *** - ****
                  </span>
                </p>
              </div>

              <div className="max-w-xl space-y-6">
                <div className="space-y-2 text-[16px] leading-7 text-neutral-700">
                  <p>
                    The current test number can only handle five users at a time.
                  </p>
                  <p>
                    If the link is busy, please wait for some time.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
