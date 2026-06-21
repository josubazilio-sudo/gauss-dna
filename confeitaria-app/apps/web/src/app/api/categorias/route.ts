import { NextResponse } from "next/server";
import { produtos } from "@/lib/db";

const categorias = [...new Set(produtos.map((p) => p.categoria))];

export async function GET() {
  return NextResponse.json(categorias.map((nome) => ({
    nome,
    produtos: produtos.filter((p) => p.categoria === nome),
  })));
}
