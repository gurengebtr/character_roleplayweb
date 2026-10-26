import { auth, signOut } from "@/auth";
import { redirect } from "next/navigation";
import Workspace from "./Workspace";

export default async function Page() {
  const session = await auth();
  if (!session?.user) redirect("/login");
  async function logout() {
    "use server";
    await signOut({ redirectTo: "/login" });
  }
  return <Workspace username={session.user.name || "You"} logout={logout} />;
}
