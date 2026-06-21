import { PrismaClient } from "@prisma/client";
import { PrismaLibSql } from "@prisma/adapter-libsql";
import { createClient } from "@libsql/client";

const libsql = createClient({ url: "file:./prisma/dev.db" });
const adapter = new PrismaLibSql(libsql);
const db = new PrismaClient({ adapter });

async function main() {
  const cat1 = await db.category.create({ data: { nome: "Bolos", slug: "bolos", descricao: "Bolos artesanais" } });
  const cat2 = await db.category.create({ data: { nome: "Doces", slug: "doces", descricao: "Doces finos" } });
  const cat3 = await db.category.create({ data: { nome: "Tortas", slug: "tortas", descricao: "Tortas doces" } });

  await db.product.createMany({ data: [
    { nome: "Bolo de Chocolate", slug: "bolo-chocolate", preco: 89.90, categoriaId: cat1.id, imagem: "🍫" },
    { nome: "Bolo de Morango", slug: "bolo-morango", preco: 94.90, categoriaId: cat1.id, imagem: "🍓" },
    { nome: "Bolo de Cenoura", slug: "bolo-cenoura", preco: 79.90, categoriaId: cat1.id, imagem: "🥕" },
    { nome: "Bolo de Limão", slug: "bolo-limao", preco: 84.90, categoriaId: cat1.id, imagem: "🍋" },
    { nome: "Brigadeiro (unid)", slug: "brigadeiro", preco: 3.50, categoriaId: cat2.id, imagem: "🍫" },
    { nome: "Cupcake", slug: "cupcake", preco: 8.90, categoriaId: cat2.id, imagem: "🧁" },
    { nome: "Torta de Morango", slug: "torta-morango", preco: 69.90, categoriaId: cat3.id, imagem: "🍰" },
    { nome: "Torta de Limão", slug: "torta-limao", preco: 64.90, categoriaId: cat3.id, imagem: "🍋" },
  ] });

  console.log("Seed concluído!");
}

main().catch(console.error).finally(() => db.$disconnect());
