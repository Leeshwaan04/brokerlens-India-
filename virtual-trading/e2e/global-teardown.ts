import { purgeE2eUser } from "./db";
export default async function globalTeardown() {
  await purgeE2eUser();
}
