type SetupPayload = {
  name?: unknown;
  businessName?: unknown;
  mail?: unknown;
  phone?: unknown;
  aim?: unknown;
};

function clean(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function digitsOnly(value: string) {
  return value.replace(/[^\d]/g, "");
}

function isValidEmail(value: string) {
  return /^\S+@\S+\.\S+$/.test(value);
}

export async function POST(request: Request) {
  let body: SetupPayload;

  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Invalid request body." }, { status: 400 });
  }

  const name = clean(body.name);
  const businessName = clean(body.businessName);
  const mail = clean(body.mail);
  const phone = clean(body.phone);
  const aim = clean(body.aim);

  if (!name || !businessName || !mail || !phone || !aim) {
    return Response.json({ error: "All fields are required." }, { status: 400 });
  }

  if (!isValidEmail(mail)) return Response.json({ error: "Invalid email." }, { status: 400 });

  const normalizedPhone = digitsOnly(phone);
  if (!normalizedPhone) {
    return Response.json({ error: "Invalid phone number." }, { status: 400 });
  }

  const apiKey = process.env.AIRTABLE_API_KEY;
  const baseId = process.env.AIRTABLE_BASE_ID;
  const tableName = process.env.AIRTABLE_SETUP_TABLE_NAME;

  if (!apiKey || !baseId || !tableName) {
    return Response.json({ error: "Setup is not configured." }, { status: 500 });
  }

  const airtableUrl = `https://api.airtable.com/v0/${baseId}/${encodeURIComponent(tableName)}`;

  try {
    const fields = {
      name,
      mail,
      "phone no": Number(normalizedPhone),
      "whats your use": `${businessName}: ${aim}`,
    };

    const response = await fetch(airtableUrl, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        fields,
      }),
    });

    if (!response.ok) {
      const details = await response.text().catch(() => "");
      console.error("Airtable setup save failed", {
        status: response.status,
        details,
        fields,
      });
      const detail = details.slice(0, 500);
      return Response.json({
        error: `Airtable error (${response.status}): ${detail}`,
      }, { status: 500 });
    }

    return Response.json({ ok: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("Airtable fetch threw:", message);
    return Response.json({
      error: `Setup request failed: ${message}`,
    }, { status: 500 });
  }
}
