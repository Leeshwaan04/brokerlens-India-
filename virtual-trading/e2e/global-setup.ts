import { purgeE2eUser } from "./db";
export default async function globalSetup() {
  await purgeE2eUser();
}
