import { auth } from "@/auth";
import { NextRequest } from "next/server";

async function proxy(
  req: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const session = await auth();
  if (!session?.user?.id)
    return Response.json({ detail: "Sign in required" }, { status: 401 });
  if (!["GET", "HEAD"].includes(req.method)) {
    const origin = req.headers.get("origin");
    if (origin !== new URL(process.env.AUTH_URL!).origin)
      return Response.json({ detail: "Origin rejected" }, { status: 403 });
  }
  const { path } = await context.params;
  const allowed = new Set([
    "characters",
    "conversations",
    "settings",
    "providers",
    "health",
  ]);
  if (
    !allowed.has(path[0]) ||
    path.some((p) => p === "." || p === ".." || p.includes("/"))
  ) {
    return Response.json({ detail: "Unknown route" }, { status: 404 });
  }
  try {
    const response = await fetch(
      `${process.env.API_URL}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`,
      {
        method: req.method,
        headers: {
          Authorization: `Bearer ${process.env.SERVICE_TOKEN}`,
          "X-User-ID": session.user.id,
          "Content-Type": "application/json",
        },
        body: ["GET", "HEAD"].includes(req.method)
          ? undefined
          : await req.text(),
        signal: AbortSignal.timeout(180000),
        cache: "no-store",
        redirect: "manual",
      },
    );
    return new Response(response.body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") || "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return Response.json(
      { detail: "API unavailable. Check the local API process." },
      { status: 502 },
    );
  }
}
export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
