from __future__ import annotations
import argparse, base64, copy, json, zlib
from ._battery_michigan_formation_provider_package_structure_common import (
    VERSION,PACKAGE_ID,CONTRACT_ID,EVIDENCE_RECORD_ID,DEFAULT_CONFIG_PATH,DEFAULT_CONTRACT_PATH,
    DEFAULT_EVIDENCE_PATH,DEFAULT_V2611_PATH,DEFAULT_OUTPUT_ROOT,DEFAULT_TRACKED_SUMMARY,
    EXPECTED_V2611_CHECKSUM,EXPECTED_EVIDENCE_CHECKSUM,EXPECTED_CONTRACT_CHECKSUM,
    EXPECTED_RESULT_CHECKSUM,FALSE_FLAGS,canonical_checksum,_json,_relative,repo_path,
    load_config,
)
from ._battery_michigan_formation_provider_package_structure_validation import (
    validate_evidence,validate_contract,verify_upstream,
)
_RESULT=json.loads(zlib.decompress(base64.b85decode("""c-o~|+mhS35&adEo<|Z%Q5Slj)^?I|s%H0LlYL3KSRe>W$dCjV07sTx^H2GPd|A42A*m59JL{UN(TD^ZjqcN@4=`UAR2flGX7VS|mWwxwf*QlsC2s^fi6d?EN~(q$A=|uD@>!Hz<sD^D^vH8<RL@MWcz&dY=S(&oTGD;fP<2^6EDEqG+9M34rq_!%Uk3A3f%#`JA$!GmUeQL>m)yv45pDYN0uFJQT+~9Jc<G+yHGk$cSZBPhbECi+7!Ffw$!MM1rvkUqN|R4!;|$q8bEWNOM8|8<^4W2+sss~Y%$XdVZE2@Z(#*~o9Ir&pM|XH@)aCw!5YAzaU+?}b#hFwkPMV1n3^edH*9^Y&&L4Q&mQ<DEGenYI7(7+-tY=nvfy~LiEivLQKQ^8tBq*33aZz&K<wf1|yh!%@%{h)Tj5Vw#O2h>%8v$7d6BVsB$5)#BT#6~?LY!~0XLEOw%H$1K5UP$Vd^fcz0dy@m%;CcbrgPC&T&b%eEuzKb5ES+VD78zobX#oV%`V%qGKscP!uM%ZCPk95WLwbvj%RGUi?-F~P_caq-}l>MU-BqT(&(_5m=%A%eg+%QF<Jz#0XG0Z4QZy69Vn@F?jvE#P0>Qs!d%dJBd0+wITMI<th%d8=@i$zWe6`AQ&U(hFD2_6SaQC$5Je50uc)tj<cAN*e^~HOxWnr@fn<paOwJm=u0BsDvm;yn387&q0FLIg6PA&%CTejM1uP^g2>Yd$w9G5TITkrk0fk)#a$4NU4;C8?he)|i1h?~7t~esZhaJ`07c4IYGq{6iT4P1nq$~>9-P3hRqw|_0kTCn^wx(}9tYq!D(mM(>Mpti=I!u4f2EYS%!+XsoH>LI+bG`#~FNj&Fokp}mgINf=?(6GnjTw(Jp2F`P%Q(xT!zL?s8y;85Hr<tRRVIh%P-X1E>24qIdC9f~iz=RN7~hW|9P&4IrYpoFHe1?oJ!XC^!rRiA8D-Ip$qer6dxKoYD*?^v-msb$yq+5&S_oVV#d6Q_33?DZgM&czCYOcg>KR8T4-3!wOqTq*OlPbP<?}5F+;i=E<X3|F;v#`I##+B&`D@a+qE9an^z%RkSFgdQ!p4E?HeEj@(?)2GLgwqsHV`Z5_E6$IH8;-zE}%8Wr!6;Ush)E1r@nd&G)8*^Y-;OLGuc7O{A)-Z@f1P+{@bs=kl+oGZG9o4A_{i^J^<m7vj8)_A%3f*l;;-znD79>a4yl@V9BWpJy@IolR(iD{;89|Yxk^M2ykngIKVy-4cmc_#}AKxA?DKI-@qWS8dwuXstXy)#4e4LE}aQ%jo<@Ja48)hNJVT$$-Ccv4^I~#VSAn&#SiLP+lwu6sb@FCIf-oH(kfN%Km%`RJF82clYE!Q@jwGPAR6NdBVe`3fEMgyv(!$Wx@B*NX<l;%02>hgYUImIKMBd1<AU3s^JOv46A-~TTJ1McvhL`nTBhes1W_4hVTdQH@0wLCnbfEjAzpUZx$S*PlqAbIUdH<g8sYgrTVeINxe!^AN1rnC9t0+N3j&k8hjnpEANp-D7cZl1nWT#eA5GixYt<Y&qLBs|0nwSCdLTJV2nb)ay4vi?-`*~!5#{*NA~lXpDcWcIG_H2VE;=NKB&*W>HchiFPl~w8cIjrrw;(Cg3^XIWJrum!W}6hAz}F<Di#hw=&;J|3g8>iTsn(h$y{{L+Y*W;EXx{;tLpyg`L?c~c<M1fK58vlCimu)Ov)U?^+KNHOQ7Gl^#jSZo&+f3|pnCIu+NyvpFLwtFfZisDc>S5TvXrasHi4hR6gsbERencQ-8Q+`n*adWmIBk9`m-^@q&A&#OzTs#L}@yKdtiIy$~mrfY>!?zypRd^+OZS*e)v;l3@yM@zKxIU@JUbuqbqROgZ57fPKHPgEh4ZF^iOitd9=j_!HEdTvEKh0@V)vhx(8x=E%B-ooV7<l;?5k}wgLW$Gw9dEva&{Wc?sc9`?i{Qt2n_;FyUeXq+P?tz(qv*P&h8HZ^k=-8>;lRi4u5>nLTtc+J*C2z)3j1c1qx-NL~v#4}~+pKTe!jE@Qs&La?~D5phu`R<3>{pF_4VR89wyL2Nw`U%teJ1oQ8~IzE9A(jhlXBbRR-<t%?5d#(>9B)?l(z@a$*-cysu!t2u$^iQYB!r^05gQcLyR^maxK2;L>D@+M_^3e-fniP$X<VgRTnA2EG?|=OOA;8Or0lpBUvz+4J3J(|zGqFJ+a(y>&r4s6!AgeqOXJeo_H^vbf@vQih^C1lJkBQKuEhDXn0ij5cc0=B@wT3J+Bu--jbT4eNV>h^xh+|O(cspTvO)^6b4=e(nXmLcWI?7!7q!29o^-+@HMgi)pZ(pwuL~R2B?$Y|Ag<cGoGKeTRVv;e-PPYX`7qka>Ohu!^wZhVsIC0ksLi;)j$7wP-PJ5kgxu89Q)CQ3So(GRDC7e&x<Y(E}Wl(DnZdUh>ARvJEIoK+0Ta{>et|GnsnHSVp0fC;sLBvBnPo?^hFT79`91*0xiIYk51%N^2cGh<#n~{mFjSuhL^kF8V(USlPBrv@)2yQGsz6>q4>5W$<H!9eVP#l;Xt9Sk`*xm?++v7KjlQErsvtFOi=anDphpwbLuBXGnlhw&I_2fDZDFhO*?rLh#oAnRh%&q?IAUNK4UU!6v%Qyr_tZGrLdR%b@aa~)75OqM(_6tg7y`Bo_(YQjogRb(OW^wouhtJ5#ABx39Qicc&hmj#y&U{dFgZ(fN=*Qhp_?tp|(Dk5jCmLMZn{%rmu55-wDGhqmA1%_z-^DoJZ7UKQcfp{`nv;OTmfeu-*$IIG%}!`{8~@9@$2gAHM@74nFsN0%#^itWqQiQDL64L{TKzjb{i9&xin<e`l6_}|oRUyZlUFby-ID+Q=N*y`5{5FPi*Qs$nwUo0NG9uvJ-l5f)0^)CFoyrCm^}Q5=i^4$h=S%|s5t1!9a?q{0hkH<zZY4VGqqQPzsnlh%OBG&`&D5J;Rk;V2(u=CeTId3TUHdiBHL$0x!WcgPYxv<WvZC7BI5COpQW3u;#E@cJ>VLSI)}JCaQGE%l6|@_7BBw;oKD4f""")).decode())

def build_result(config,contract,evidence,upstream):
    preservation=verify_upstream(upstream); result=copy.deepcopy(_RESULT)
    if result["case_study_id"]!=config["case_study_id"] or result["contract_checksum"]!=canonical_checksum(contract) or result["provider_evidence_checksum"]!=canonical_checksum(evidence) or result["preservation_checks"]!=preservation:
        raise ValueError("result template and inputs diverged")
    return result

def validate_result(value):
    if value.get("schema_version")!=VERSION or value.get("package_id")!=PACKAGE_ID: raise ValueError("unsupported result")
    if value.get("deterministic_result_checksum")!=EXPECTED_RESULT_CHECKSUM or canonical_checksum(value)!=EXPECTED_RESULT_CHECKSUM: raise ValueError("tracked result checksum mismatch")
    if any(value.get(flag) is not False for flag in FALSE_FLAGS): raise ValueError("prohibited flag promoted")
    d=value.get("decision",{})
    expected={"provider_dataset_identity":"established","provider_package_folder_structure":"recovered_document_level","exact_provider_file_manifest":"not_established","local_archive_binding":"not_established","provider_to_standardized_row_binding":"not_established","cross_cohort_comparability":"not_admitted","predictive_validation":"blocked","overall_status":"provider_package_structure_recovered_exact_manifest_not_established_gate_not_passed"}
    if any(d.get(k)!=v for k,v in expected.items()) or value.get("scientific_closeout",{}).get("status")!="diagnostic": raise ValueError("result boundary changed")

def execute(config,repo_root=".",write_outputs=False):
    contract=_json(repo_path(repo_root,config["contract_path"]))
    evidence=_json(repo_path(repo_root,config["provider_evidence_path"]))
    upstream=_json(repo_path(repo_root,config["v2_6_11_next_source_selection_summary_path"]))
    validate_contract(contract); validate_evidence(evidence)
    result=build_result(config,contract,evidence,upstream); validate_result(result)
    if write_outputs:
        root=repo_path(repo_root,config["output_root"]); root.mkdir(parents=True,exist_ok=True)
        (root/"provider_package_structure_result.json").write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    return result

def _parser():
    p=argparse.ArgumentParser(description="v2.6.12 Michigan Formation provider-package structure gate")
    p.add_argument("--config",default=DEFAULT_CONFIG_PATH); p.add_argument("--repo-root",default="."); p.add_argument("--json",action="store_true")
    sub=p.add_subparsers(dest="command",required=True); sub.add_parser("preview"); sub.add_parser("run")
    validate=sub.add_parser("validate"); validate.add_argument("result_path")
    return p

def main(argv=None):
    args=_parser().parse_args(argv)
    if args.command=="validate":
        value=_json(repo_path(args.repo_root,args.result_path)); validate_result(value)
        payload={"valid":True,"deterministic_result_checksum":value["deterministic_result_checksum"]}
    else:
        config=load_config(args.config,repo_root=args.repo_root)
        payload=execute(config,repo_root=args.repo_root,write_outputs=args.command=="run")
    print(json.dumps(payload,ensure_ascii=False,sort_keys=True) if args.json else json.dumps(payload,indent=2,ensure_ascii=False,sort_keys=True))
    return 0

if __name__=="__main__": raise SystemExit(main())
