import { ArrowRight } from "lucide-react";
import { Button, Modal } from "../ui";
import { ProductVisual } from "./ProductVisual";

export function LandedCostPreviewModal({ open, onClose, onOpenCalculator }: { open: boolean; onClose: () => void; onOpenCalculator: () => void }) {
  return (
    <Modal open={open} title="Landed cost preview" onClose={onClose}>
      <div className="modal-product"><ProductVisual glyph="COIL" /><div><strong>SS 304 Cold Rolled Coil</strong><small>5,000 kg · Mumbai to Vadodara</small></div></div>
      <div className="modal-cost"><span><small>Material</small><strong>₹10,74,000</strong></span><span><small>Freight</small><strong>₹21,250</strong></span><span><small>Insurance & handling</small><strong>₹3,180</strong></span><span><small>Landed cost</small><strong>₹10,98,430</strong></span></div>
      <div className="modal-actions"><Button variant="secondary" onClick={onClose}>Close</Button><Button onClick={onOpenCalculator}>Open full calculator <ArrowRight size={16}/></Button></div>
    </Modal>
  );
}
