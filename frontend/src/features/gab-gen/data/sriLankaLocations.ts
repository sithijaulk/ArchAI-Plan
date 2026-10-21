export interface DistrictOption {
  name: string;
  authorities: {
    type: 'Municipal Council' | 'Urban Council' | 'Pradeshiya Sabha';
    name: string;
  }[];
}

export interface ProvinceOption {
  name: string;
  districts: Record<string, DistrictOption>;
}

export const SRI_LANKA_ADMIN_DATA: Record<string, ProvinceOption> = {
  "Western": {
    name: "Western",
    districts: {
      "Colombo": {
        name: "Colombo",
        authorities: [
          { type: "Municipal Council", name: "Colombo Municipal Council" },
          { type: "Municipal Council", name: "Dehiwala-Mount Lavinia Municipal Council" },
          { type: "Municipal Council", name: "Sri Jayawardenepura Kotte Municipal Council" },
          { type: "Municipal Council", name: "Kaduwela Municipal Council" },
          { type: "Municipal Council", name: "Moratuwa Municipal Council" },
          { type: "Urban Council", name: "Kolonnawa Urban Council" },
          { type: "Urban Council", name: "Seethawaka Urban Council" },
          { type: "Urban Council", name: "Kesbewa Urban Council" },
          { type: "Urban Council", name: "Maharagama Urban Council" },
          { type: "Urban Council", name: "Boralesgamuwa Urban Council" },
          { type: "Pradeshiya Sabha", name: "Kotikawatta Mulleriyawa Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Homagama Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Seethawaka Pradeshiya Sabha" }
        ]
      },
      "Gampaha": {
        name: "Gampaha",
        authorities: [
          { type: "Municipal Council", name: "Negombo Municipal Council" },
          { type: "Municipal Council", name: "Gampaha Municipal Council" },
          { type: "Urban Council", name: "Wattala-Mabole Urban Council" },
          { type: "Urban Council", name: "Ja-Ela Urban Council" },
          { type: "Urban Council", name: "Peliyagoda Urban Council" },
          { type: "Urban Council", name: "Katunayake Seeduwa Urban Council" },
          { type: "Urban Council", name: "Minuwangoda Urban Council" },
          { type: "Pradeshiya Sabha", name: "Kelaniya Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Wattala Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Ja-Ela Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Gampaha Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Biyagama Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Mahara Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Dompe Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Mirigama Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Minuwangoda Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Divulapitiya Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Katana Pradeshiya Sabha" }
        ]
      },
      "Kalutara": {
        name: "Kalutara",
        authorities: [
          { type: "Urban Council", name: "Kalutara Urban Council" },
          { type: "Urban Council", name: "Panadura Urban Council" },
          { type: "Urban Council", name: "Horana Urban Council" },
          { type: "Urban Council", name: "Beruwala Urban Council" },
          { type: "Pradeshiya Sabha", name: "Panadura Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Kalutara Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Horana Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Beruwala Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Bandaragama Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Matugama Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Bulathsinhala Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Dodangoda Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Madurawala Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Palindanuwara Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Walallawita Pradeshiya Sabha" },
          { type: "Pradeshiya Sabha", name: "Agalawatta Pradeshiya Sabha" }
        ]
      }
    }
  },
  "Central": {
    name: "Central",
    districts: {
      "Kandy": {
        name: "Kandy",
        authorities: [
          { type: "Municipal Council", name: "Kandy Municipal Council" },
          { type: "Urban Council", name: "Gampola Urban Council" },
          { type: "Pradeshiya Sabha", name: "Harispattuwa Pradeshiya Sabha" }
        ]
      },
      "Matale": {
        name: "Matale",
        authorities: [
          { type: "Municipal Council", name: "Matale Municipal Council" },
          { type: "Pradeshiya Sabha", name: "Matale Pradeshiya Sabha" }
        ]
      },
      "Nuwara Eliya": {
        name: "Nuwara Eliya",
        authorities: [
          { type: "Municipal Council", name: "Nuwara Eliya Municipal Council" },
          { type: "Urban Council", name: "Hatton-Dickoya Urban Council" }
        ]
      }
    }
  },
  "Southern": {
    name: "Southern",
    districts: {
      "Galle": {
        name: "Galle",
        authorities: [
          { type: "Municipal Council", name: "Galle Municipal Council" },
          { type: "Urban Council", name: "Ambalangoda Urban Council" },
          { type: "Pradeshiya Sabha", name: "Bope-Poddala Pradeshiya Sabha" }
        ]
      },
      "Matara": {
        name: "Matara",
        authorities: [
          { type: "Municipal Council", name: "Matara Municipal Council" },
          { type: "Urban Council", name: "Weligama Urban Council" }
        ]
      },
      "Hambantota": {
        name: "Hambantota",
        authorities: [
          { type: "Urban Council", name: "Tangalle Urban Council" },
          { type: "Urban Council", name: "Hambantota Urban Council" }
        ]
      }
    }
  }
};
