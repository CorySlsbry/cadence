import type { Metadata } from "next";
import { FacelessClient } from "./faceless-client";

export const metadata: Metadata = {
  title: "Faceless studio — CloutHook",
  description: "Topic in, finished faceless short out — AI scenes, premium narration, karaoke captions.",
};

export default function FacelessPage() {
  return <FacelessClient />;
}
