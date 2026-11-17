import { NextRequest, NextResponse } from "next/server";

const getPaths = [
  /^services$/,
  /^simulations$/,
  /^workflows$/,
  /^monitoring$/,
  /^models$/,
  /^research\/summary$/,
  /^services\/[a-f0-9-]+$/,
  /^simulations\/[a-f0-9-]+$/,
  /^workflows\/[a-f0-9-]+$/,
];
const postPaths = [
  /^intents$/,
  /^intents\/parse$/,
  /^simulations\/run$/,
  /^workflows$/,
  /^workflows\/[a-f0-9-]+\/approve$/,
  /^models\/[a-f0-9]+\/promote-shadow$/,
];

async function relay(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const target = path.join("/");
  const allowed = request.method === "GET" ? getPaths : postPaths;
  if (!allowed.some((pattern) => pattern.test(target))) {
    return NextResponse.json({ detail: "route not allowed" }, { status: 404 });
  }
  const base = process.env.SOVEREIGN_API_BASE_URL;
  const tenantToken = process.env.SOVEREIGN_DASHBOARD_TENANT_TOKEN;
  if (!base || !tenantToken) {
    return NextResponse.json(
      { detail: "Dashboard API connection is not configured" },
      { status: 503 },
    );
  }
  const approval = /(?:\/approve|\/promote-shadow)$/.test(target);
  const approverToken = process.env.SOVEREIGN_DASHBOARD_APPROVER_TOKEN;
  if (approval && !approverToken) {
    return NextResponse.json(
      { detail: "Separate approver credential is not configured" },
      { status: 403 },
    );
  }
  try {
    const url = new URL(`/v1/${target}`, base);
    if (request.method === "GET") {
      for (const key of ["limit", "offset"]) {
        const value = request.nextUrl.searchParams.get(key);
        if (value !== null) url.searchParams.set(key, value);
      }
    }
    const response = await fetch(url, {
      method: request.method,
      cache: "no-store",
      headers: {
        "X-Tenant-Token": tenantToken,
        ...(approval ? { "X-Approver-Token": approverToken! } : {}),
        ...(request.method === "POST"
          ? {
              "Content-Type": "application/json",
              "Idempotency-Key": crypto.randomUUID(),
            }
          : {}),
      },
      body: request.method === "POST" ? await request.text() : undefined,
      signal: AbortSignal.timeout(10000),
    });
    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      { detail: "Backend unavailable" },
      { status: 502 },
    );
  }
}

export const GET = relay;
export const POST = relay;
