import logo from "../../assets/new_logo.png";

export function Logo() {
  return (
    <div className="brand" aria-label="Plenza by HCP Plastene Bulkpack Ltd.">
      <img className="brand__logo" src={logo} alt="" />
      <div><strong data-brand-mark>PLENZA</strong><small>BY HCP PLASTENE BULKPACK LTD.</small></div>
    </div>
  );
}
