import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({ latest: null }, { status: 200 });
}
