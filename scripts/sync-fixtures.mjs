import { copyFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = resolve(root, "fixtures");
const destination = resolve(root, "frontend", "public", "fixtures");
const fixtures = ["stripe.json", "openai-tools.json", "twilio-signature-v2.json"];

await mkdir(destination, { recursive: true });
await Promise.all(fixtures.map((name) => copyFile(resolve(source, name), resolve(destination, name))));
console.log(`synced ${fixtures.length} canonical scenario fixtures`);
